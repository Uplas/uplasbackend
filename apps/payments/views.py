from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime
from django.db import transaction # Import transaction
import stripe

from rest_framework import generics, viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError, NotFound

from .models import SubscriptionPlan, UserSubscription, Transaction
from .serializers import (
    SubscriptionPlanSerializer, UserSubscriptionSerializer, TransactionSerializer,
    CreateSubscriptionCheckoutSessionSerializer
    # StripeWebhookEventSerializer is conceptual, not directly used for request validation here
)
from django.contrib.auth import get_user_model # Use get_user_model

User = get_user_model()

# Initialize Stripe API client (ensure keys are in settings)
if hasattr(settings, 'STRIPE_SECRET_KEY') and settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY
else:
    # This will cause errors if Stripe is actually called.
    # For GitHub-only phase, we'll mock Stripe calls in tests.
    print("WARNING: STRIPE_SECRET_KEY is not set in Django settings.")
    stripe.api_key = "sk_test_yourstripek...." # Fallback dummy key for module to load

STRIPE_WEBHOOK_SECRET = getattr(settings, 'STRIPE_WEBHOOK_SECRET_PAYMENTS', None)
if not STRIPE_WEBHOOK_SECRET:
    print("WARNING: STRIPE_WEBHOOK_SECRET_PAYMENTS is not set. Webhook verification will fail.")

class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionPlan.objects.filter(is_active=True).order_by('display_order', 'price')
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny]

class UserSubscriptionViewSet(viewsets.ReadOnlyModelViewSet): # User can only read their own sub
    serializer_class = UserSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # A user has one primary subscription via OneToOneField 'subscription' on User model
        # or if UserSubscription.user is OneToOneField.
        # If UserSubscription.user is ForeignKey, then filter by user.
        # Based on our model: user = models.OneToOneField(User, ..., related_name='subscription')
        # So, a user can only have one UserSubscription object.
        user_subscription = getattr(self.request.user, 'subscription', None)
        if user_subscription:
            return UserSubscription.objects.filter(pk=user_subscription.pk).select_related('plan', 'user')
        return UserSubscription.objects.none() # Return empty queryset if no subscription

    def list(self, request, *args, **kwargs): # Effectively a retrieve for the user's single subscription
        instance = self.get_queryset().first() # Get the first (and only) item
        if not instance:
            return Response({"detail": _("No active subscription found.")}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='cancel-subscription') # Changed from 'cancel' to avoid conflict with potential 'cancel' named resource
    def cancel_my_subscription(self, request, *args, **kwargs): # Renamed for clarity
        user_sub = self.get_queryset().filter(status__in=['active', 'trialing', 'past_due', 'unpaid']).first()
        if not user_sub:
            return Response({'detail': _('No active or resumable subscription to cancel.')}, status=status.HTTP_404_NOT_FOUND)

        if not user_sub.stripe_subscription_id:
            # This might be an internal subscription or one not managed by Stripe.
            # Handle manually or disallow cancellation via this API for such cases.
            user_sub.status = 'canceled'
            user_sub.cancel_at_period_end = False # Immediate cancel for non-Stripe
            user_sub.canceled_at = timezone.now()
            user_sub.ended_at = timezone.now() # Mark as ended
            user_sub.save()
            # User model update will be handled by user_sub.save()
            return Response({'detail': _('Subscription marked as canceled internally.')}, status=status.HTTP_200_OK)

        try:
            # For Stripe, it's best to cancel at period end to allow user to use remaining time.
            stripe.Subscription.modify(
                user_sub.stripe_subscription_id,
                cancel_at_period_end=True
            )
            user_sub.cancel_at_period_end = True
            # Status update to 'canceled' will come via webhook when period actually ends.
            # We are just recording the intent here.
            user_sub.save(update_fields=['cancel_at_period_end', 'updated_at'])
            return Response({'detail': _('Your subscription is set to cancel at the end of the current billing period.')}, status=status.HTTP_200_OK)
        except stripe.error.StripeError as e:
            # Log the error: print(f"Stripe error during cancel_my_subscription: {e}")
            return Response({'detail': _(f'Could not request cancellation with payment provider: {str(e)} Please try again or contact support.')}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Log the error: print(f"Unexpected error during cancel_my_subscription: {e}")
            return Response({'detail': _('An unexpected error occurred. Please try again later.')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).select_related(
            'user_subscription__plan' # For basic plan info if nested in serializer
        ).order_by('-processed_at', '-created_at')


class CreateCheckoutSessionView(generics.GenericAPIView):
    serializer_class = CreateSubscriptionCheckoutSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        plan_id = serializer.validated_data['plan_id'] # This is already validated to be a valid UUID
        success_url = serializer.validated_data['success_url']
        cancel_url = serializer.validated_data['cancel_url']
        
        user = request.user
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True) # Already validated by serializer, but good to fetch
        except SubscriptionPlan.DoesNotExist: # Should not happen if serializer validation is correct
            raise NotFound(_("Selected subscription plan not found or is inactive."))

        if not plan.stripe_price_id: # Also validated by serializer
             raise DRFValidationError(_("This plan is not configured for online payment."))

        stripe_customer_id = user.stripe_customer_id
        
        if not stripe_customer_id:
            try:
                customer_params = {
                    'email': user.email,
                    'name': user.full_name or user.username,
                    'metadata': {'uplas_user_id': str(user.id)}
                }
                # Add address, phone if collected and useful for Stripe/tax
                # if user.country and hasattr(settings, 'STRIPE_SUPPORTED_COUNTRIES_FOR_ADDRESS') and user.country in settings.STRIPE_SUPPORTED_COUNTRIES_FOR_ADDRESS:
                #     customer_params['address'] = {'country': user.country, 'city': user.city}

                customer = stripe.Customer.create(**customer_params)
                stripe_customer_id = customer.id
                user.stripe_customer_id = stripe_customer_id
                user.save(update_fields=['stripe_customer_id'])
            except stripe.error.StripeError as e:
                # Log error: print(f"Stripe customer creation error: {e}")
                return Response({'error': _(f'Could not set up payment profile: {str(e)}')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        line_items = [{'price': plan.stripe_price_id, 'quantity': 1}]
        checkout_session_params = {
            'customer': stripe_customer_id,
            'payment_method_types': ['card'], # Or ['card', 'paypal'], etc.
            'line_items': line_items,
            'mode': 'subscription', # For recurring plans
            'success_url': success_url + '?session_id={CHECKOUT_SESSION_ID}', # Pass session ID back
            'cancel_url': cancel_url,
            'metadata': {
                'uplas_user_id': str(user.id),
                'uplas_plan_id': str(plan.id),
            }
        }
        # Handle trials if the plan is a trial plan or if you have trial logic
        # if plan.has_trial_period: # Assuming a field on SubscriptionPlan model
        #    checkout_session_params['subscription_data'] = {'trial_period_days': plan.trial_days}

        try:
            checkout_session = stripe.checkout.Session.create(**checkout_session_params)
            
            # Optionally, pre-create a UserSubscription record with 'incomplete' status.
            # This helps track initiated checkouts.
            UserSubscription.objects.update_or_create(
                user=user, # Since user is OneToOne with UserSubscription
                defaults={
                    'plan': plan,
                    'stripe_customer_id': stripe_customer_id, # Store customer ID with the sub attempt
                    'status': 'incomplete', 
                    # 'stripe_checkout_session_id': checkout_session.id, # Add this field to UserSubscription if needed
                    'current_period_start': None, # Will be set by webhook
                    'current_period_end': None,   # Will be set by webhook
                }
            )
            return Response({'checkout_session_id': checkout_session.id, 'checkout_url': checkout_session.url}, status=status.HTTP_200_OK)
        except stripe.error.StripeError as e:
            # Log error: print(f"Stripe checkout session creation error: {e}")
            return Response({'error': _(f'Could not initiate payment session: {str(e)}')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            # Log error: print(f"Unexpected error creating checkout session: {e}")
            return Response({'error': _('An unexpected error occurred while initiating payment.')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StripeWebhookView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_user_from_stripe_data(self, event_data):
        """Helper to find Uplas user from Stripe customer ID or metadata."""
        stripe_customer_id = event_data.get('customer')
        user = None
        if stripe_customer_id:
            try:
                user = User.objects.get(stripe_customer_id=stripe_customer_id)
            except User.DoesNotExist:
                 # Fallback: check metadata if customer ID wasn't on user yet (e.g., from checkout session)
                metadata = event_data.get('metadata', {})
                uplas_user_id = metadata.get('uplas_user_id')
                if uplas_user_id:
                    try:
                        user = User.objects.get(pk=uplas_user_id)
                        # If found via metadata and user doesn't have stripe_customer_id yet, update it
                        if user and not user.stripe_customer_id and stripe_customer_id:
                            user.stripe_customer_id = stripe_customer_id
                            user.save(update_fields=['stripe_customer_id'])
                    except User.DoesNotExist:
                        print(f"Webhook: User with uplas_user_id {uplas_user_id} from metadata not found.")
                else:
                    print(f"Webhook: Stripe customer ID {stripe_customer_id} not found on any Uplas user and no uplas_user_id in metadata.")
        return user

    @transaction.atomic # Ensure all DB operations for a webhook are atomic
    def _handle_checkout_session_completed(self, event_data):
        session = event_data # event_data is the session object
        print(f"Webhook: Handling checkout.session.completed for session {session.get('id')}")
        
        stripe_customer_id = session.get('customer')
        stripe_subscription_id = session.get('subscription')
        metadata = session.get('metadata', {})
        uplas_user_id = metadata.get('uplas_user_id')
        uplas_plan_id = metadata.get('uplas_plan_id')
        payment_status = session.get('payment_status')

        user = self._get_user_from_stripe_data(session)
        if not user:
            print(f"Webhook Error (checkout.session.completed): User not found for session {session.get('id')}.")
            return # Cannot proceed without a user

        plan = None
        if uplas_plan_id:
            try:
                plan = SubscriptionPlan.objects.get(pk=uplas_plan_id)
            except SubscriptionPlan.DoesNotExist:
                print(f"Webhook Error (checkout.session.completed): Plan with ID {uplas_plan_id} from metadata not found.")
                # This is problematic, might need manual intervention or a default action

        if payment_status == 'paid' and stripe_subscription_id:
            # The actual subscription record is usually created/updated by 'customer.subscription.created/updated' events.
            # This event confirms the checkout itself. We can update our preliminary UserSubscription record.
            user_sub, created = UserSubscription.objects.update_or_create(
                user=user, # Relies on OneToOne user-subscription link
                defaults={
                    'plan': plan, # Update plan if it was preliminary
                    'stripe_subscription_id': stripe_subscription_id,
                    'stripe_customer_id': stripe_customer_id, # Ensure it's set
                    # Status will be set by customer.subscription.created/updated event.
                    # If this event comes before customer.subscription.created, set to a temp active-like state.
                    # 'status': 'active', # Or defer to subscription event
                    # 'current_period_start': timezone.now(), # Approximate, will be overwritten by sub event
                    # 'current_period_end': # Cannot determine from session alone typically
                }
            )
            print(f"Webhook: Checkout session {session.get('id')} processed for user {user.email}. UserSubscription {'created' if created else 'updated'}.")
        elif payment_status != 'paid':
            # Checkout completed but payment not successful (e.g. 'unpaid', 'no_payment_required' for trials without upfront)
            # Update our UserSubscription to 'incomplete' or based on actual Stripe sub status if available.
            UserSubscription.objects.filter(user=user).update(status='incomplete') # Or a more specific status
            print(f"Webhook: Checkout session {session.get('id')} for user {user.email} completed with payment_status: {payment_status}.")
        else:
            print(f"Webhook: Checkout session {session.get('id')} for user {user.email} has no subscription ID (mode might not be 'subscription' or other issue).")


    @transaction.atomic
    def _handle_customer_subscription_event(self, event_data, event_type): # Handles created, updated, deleted
        sub = event_data # event_data is the subscription object
        print(f"Webhook: Handling {event_type} for subscription {sub.get('id')}")
        
        user = self._get_user_from_stripe_data(sub)
        if not user:
            print(f"Webhook Error ({event_type}): User not found for Stripe customer {sub.get('customer')}, subscription {sub.get('id')}.")
            return

        stripe_price_id = None
        if sub.get('items') and sub['items'].get('data'):
            # A subscription can have multiple items, typically one for simple plans.
            # We're assuming the first item's price is the one for our SubscriptionPlan.
            primary_item = sub['items']['data'][0] if sub['items']['data'] else None
            if primary_item and primary_item.get('price'):
                stripe_price_id = primary_item['price']['id']
        
        plan = None
        if stripe_price_id:
            try:
                plan = SubscriptionPlan.objects.get(stripe_price_id=stripe_price_id)
            except SubscriptionPlan.DoesNotExist:
                print(f"Webhook Warning ({event_type}): Plan for Stripe Price ID {stripe_price_id} not found. Sub ID: {sub.get('id')}")
                # You might want to create a placeholder plan or flag this for admin review.
                # For now, we proceed, UserSubscription.plan might remain None or previous value.

        subscription_status = sub.get('status') # e.g., active, trialing, past_due, canceled, unpaid, incomplete
        
        # Map Stripe status to our model's status choices if they differ significantly
        # For now, assuming a direct mapping or similar enough terms.
        
        user_sub_defaults = {
            'stripe_customer_id': sub.get('customer'),
            'status': subscription_status,
            'current_period_start': datetime.fromtimestamp(sub['current_period_start'], tz=timezone.utc) if sub.get('current_period_start') else None,
            'current_period_end': datetime.fromtimestamp(sub['current_period_end'], tz=timezone.utc) if sub.get('current_period_end') else None,
            'cancel_at_period_end': sub.get('cancel_at_period_end', False),
            'canceled_at': datetime.fromtimestamp(sub['canceled_at'], tz=timezone.utc) if sub.get('canceled_at') else None,
            'ended_at': datetime.fromtimestamp(sub.get('ended_at'), tz=timezone.utc) if sub.get('ended_at') else None, # For subscriptions that naturally end
            'trial_start_date': datetime.fromtimestamp(sub['trial_start'], tz=timezone.utc) if sub.get('trial_start') else None,
            'trial_end_date': datetime.fromtimestamp(sub['trial_end'], tz=timezone.utc) if sub.get('trial_end') else None,
        }
        if plan: # Only update plan if found
            user_sub_defaults['plan'] = plan
        
        # Use stripe_subscription_id for uniqueness if user can have multiple past subscriptions.
        # But our model user is OneToOneField to UserSubscription, so user is the key.
        user_sub, created = UserSubscription.objects.update_or_create(
            user=user, # This assumes one active subscription per user managed by this OneToOne
            # stripe_subscription_id=sub.get('id'), # Use this if User can have multiple UserSubscription records
            defaults=user_sub_defaults
        )
        
        # If it's a new subscription being created via webhook and start_date isn't set by Stripe's 'created' field.
        if created and sub.get('start_date') and not user_sub.start_date:
            user_sub.start_date = datetime.fromtimestamp(sub['start_date'], tz=timezone.utc)
            user_sub.save(update_fields=['start_date']) # User model update handled by full save

        # For 'customer.subscription.deleted', Stripe sends the final state of the subscription
        # which often has status='canceled' and 'canceled_at' set.
        # Our logic above should handle this by updating the status and canceled_at.
        # 'ended_at' is also important for subscriptions that complete their term.
        
        print(f"Webhook: UserSubscription for user {user.email} {'created' if created else 'updated'} by {event_type}. New status: {subscription_status}. Sub ID: {sub.get('id')}")
        # user_sub.save() will trigger the update to User model's premium status.

    @transaction.atomic
    def _handle_invoice_payment_succeeded(self, event_data):
        invoice = event_data
        print(f"Webhook: Handling invoice.payment_succeeded for invoice {invoice.get('id')}")
        user = self._get_user_from_stripe_data(invoice)
        if not user:
            print(f"Webhook Error (invoice.payment_succeeded): User not found for Stripe customer {invoice.get('customer')}.")
            return

        user_sub = None
        if invoice.get('subscription'):
            try: # Try to link to an existing UserSubscription record
                user_sub = UserSubscription.objects.get(stripe_subscription_id=invoice['subscription'], user=user)
            except UserSubscription.DoesNotExist:
                print(f"Webhook Info (invoice.payment_succeeded): UserSubscription not found for Stripe sub ID {invoice['subscription']}. This might be the first payment for a new sub, which will be created by customer.subscription.created.")
                # It's okay if not found, transaction can still be recorded. Subscription event will create/update UserSubscription.

        # Determine transaction type
        trans_type = 'subscription_renewal'
        if invoice.get('billing_reason') == 'subscription_create':
            trans_type = 'subscription_signup'
        elif not invoice.get('subscription'): # If no subscription, could be a one-time invoice
            trans_type = 'one_time_purchase' # Or a more generic 'payment_intent'

        Transaction.objects.update_or_create(
            # Use a unique Stripe ID from the invoice to prevent duplicate transactions for the same event
            # Payment Intent ID is usually the best for this if available from the invoice
            stripe_payment_intent_id=invoice.get('payment_intent'), 
            defaults={
                'user': user,
                'user_subscription': user_sub,
                'stripe_charge_id': invoice.get('charge'), # May be null if PI is used
                'stripe_invoice_id': invoice.get('id'),
                'transaction_type': trans_type,
                'status': 'succeeded', # From event type
                'amount': invoice['amount_paid'] / 100.0, # Stripe amounts are in cents
                'currency': invoice['currency'].upper(),
                'payment_method_details': {'card_brand': invoice.get('charge_details', {}).get('card', {}).get('brand'), # Example, structure varies
                                           'card_last4': invoice.get('charge_details', {}).get('card', {}).get('last4')},
                'description': invoice.get('description') or f"Payment for invoice {invoice.get('id')}",
                'processed_at': datetime.fromtimestamp(invoice['status_transitions']['paid_at'], tz=timezone.utc) if invoice.get('status_transitions', {}).get('paid_at') else timezone.now()
            }
        )
        print(f"Webhook: Transaction 'succeeded' recorded for invoice {invoice.get('id')}, user {user.email}.")

    @transaction.atomic
    def _handle_invoice_payment_failed(self, event_data):
        invoice = event_data
        print(f"Webhook: Handling invoice.payment_failed for invoice {invoice.get('id')}")
        user = self._get_user_from_stripe_data(invoice)
        if not user:
            print(f"Webhook Error (invoice.payment_failed): User not found for Stripe customer {invoice.get('customer')}.")
            return

        user_sub = None
        if invoice.get('subscription'):
            try:
                user_sub = UserSubscription.objects.get(stripe_subscription_id=invoice['subscription'], user=user)
            except UserSubscription.DoesNotExist:
                print(f"Webhook Info (invoice.payment_failed): UserSubscription not found for Stripe sub ID {invoice['subscription']}.")

        # The subscription status (e.g., 'past_due', 'unpaid') is typically updated by 'customer.subscription.updated' event.
        # Here we just record the failed transaction.
        charge_error = invoice.get('last_finalization_error') or invoice.get('charge_details',{}).get('failure_details') or {} # Structure varies
        
        Transaction.objects.update_or_create(
            stripe_payment_intent_id=invoice.get('payment_intent'), # Use PI if available for idempotency
            defaults={
                'user': user,
                'user_subscription': user_sub,
                'stripe_charge_id': invoice.get('charge'),
                'stripe_invoice_id': invoice.get('id'),
                'transaction_type': 'subscription_renewal' if user_sub else 'payment_intent',
                'status': 'failed',
                'amount': invoice['amount_due'] / 100.0,
                'currency': invoice['currency'].upper(),
                'error_message': charge_error.get('message', 'Unknown payment failure.'),
                'processed_at': timezone.now() # Time this webhook processed the failure
            }
        )
        print(f"Webhook: Transaction 'failed' recorded for invoice {invoice.get('id')}, user {user.email}.")
        # Optionally: Send notification to user about payment failure.

    def post(self, request, *args, **kwargs):
        if not STRIPE_WEBHOOK_SECRET:
            print("Webhook Error: Stripe webhook secret is not configured.")
            return Response({'error': 'Webhook secret not configured on server.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        event = None

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except ValueError as e: # Invalid payload
            print(f"Webhook ValueError: {e}")
            return Response({'error': 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e: # Invalid signature
            print(f"Webhook SignatureVerificationError: {e}")
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Webhook general construction error: {e}")
            return Response({'error': f'Webhook construction error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        event_type = event['type']
        event_data = event['data']['object'] # The Stripe object related to the event

        # For idempotency: check if event.id has been processed before.
        # E.g., cache processed_event_ids or store them in a simple model.
        # If processed_event_ids.exists(event.id): return Response({'status': 'already processed'}, status=status.HTTP_200_OK)
        
        # Print event for debugging in development
        # print(f"Received Stripe webhook: ID: {event.get('id')}, Type: {event_type}")

        handler_map = {
            'checkout.session.completed': self._handle_checkout_session_completed,
            'customer.subscription.created': lambda data: self._handle_customer_subscription_event(data, 'customer.subscription.created'),
            'customer.subscription.updated': lambda data: self._handle_customer_subscription_event(data, 'customer.subscription.updated'),
            'customer.subscription.deleted': lambda data: self._handle_customer_subscription_event(data, 'customer.subscription.deleted'), # Stripe sends final sub object
            'invoice.payment_succeeded': self._handle_invoice_payment_succeeded,
            'invoice.payment_failed': self._handle_invoice_payment_failed,
            # Add more handlers as needed:
            # 'customer.subscription.trial_will_end': self._handle_trial_will_end,
            # 'payment_intent.succeeded': self._handle_payment_intent_succeeded,
            # 'payment_intent.payment_failed': self._handle_payment_intent_payment_failed,
            # 'charge.refunded': self._handle_charge_refunded,
        }

        handler = handler_map.get(event_type)
        if handler:
            try:
                handler(event_data)
                # Mark event as processed if using idempotency tracking
            except Exception as e:
                print(f"Error processing webhook event {event.get('id')} ({event_type}): {str(e)}")
                # Consider specific logging for critical errors
                # Return 500 so Stripe retries for transient errors.
                # If it's a non-transient error (e.g., bad data we can't handle),
                # you might eventually want to return 200 after logging to stop retries.
                return Response({'error': 'Internal server error while processing webhook.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            print(f'Webhook: Unhandled event type: {event_type}')

        return Response({'status': 'success'}, status=status.HTTP_200_OK)
