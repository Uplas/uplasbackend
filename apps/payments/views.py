from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime
import stripe # Stripe Python library: pip install stripe

from rest_framework import generics, viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError

from .models import SubscriptionPlan, UserSubscription, Transaction
from .serializers import (
    SubscriptionPlanSerializer, UserSubscriptionSerializer, TransactionSerializer,
    CreateSubscriptionCheckoutSessionSerializer
)
from apps.users.models import User # For updating user's Stripe customer ID

# Initialize Stripe API client
stripe.api_key = settings.STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET # For verifying webhook signatures

class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for listing available subscription plans.
    Frontend: upricing.js makes a call to /api/payments/plans/ 
    """
    queryset = SubscriptionPlan.objects.filter(is_active=True).order_by('display_order', 'price')
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny] # Plans are public

class UserSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for retrieving the current user's subscription details.
    """
    serializer_class = UserSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserSubscription.objects.filter(user=self.request.user).select_related('plan', 'user')

    def list(self, request, *args, **kwargs):
        # A user typically has one active subscription record.
        # If you allow multiple, this might need adjustment or use retrieve.
        instance = self.get_queryset().first()
        if not instance:
            return Response({"detail": "No active subscription found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], url_path='cancel')
    def cancel_subscription(self, request, *args, **kwargs):
        user_sub = self.get_queryset().filter(status__in=['active', 'trialing', 'past_due']).first()
        if not user_sub:
            return Response({'detail': 'No active subscription to cancel.'}, status=status.HTTP_404_NOT_FOUND)

        if not user_sub.stripe_subscription_id:
            return Response({'detail': 'This subscription cannot be managed automatically. Please contact support.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Option 1: Cancel immediately
            # stripe.Subscription.delete(user_sub.stripe_subscription_id)
            # user_sub.status = 'canceled'
            # user_sub.canceled_at = timezone.now()
            # user_sub.cancel_at_period_end = False # Explicitly set if cancelling now

            # Option 2: Cancel at period end (recommended for better UX)
            stripe.Subscription.modify(
                user_sub.stripe_subscription_id,
                cancel_at_period_end=True
            )
            user_sub.cancel_at_period_end = True
            # The status will change to 'canceled' via webhook when the period actually ends.
            # For now, we reflect the intent.
            
            user_sub.save()
            return Response({'detail': 'Subscription set to cancel at the end of the current billing period.'}, status=status.HTTP_200_OK)
        except stripe.error.StripeError as e:
            return Response({'detail': f'Stripe error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'detail': f'An unexpected error occurred: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for listing user's payment transactions.
    """
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).select_related('user_subscription__plan').order_by('-created_at')


class CreateCheckoutSessionView(generics.GenericAPIView):
    """
    Creates a Stripe Checkout session for a subscription plan.
    Frontend calls this when user clicks "Subscribe" or "Upgrade".
    /api/payments/create-checkout-session/ 
    """
    serializer_class = CreateSubscriptionCheckoutSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        plan_id = serializer.validated_data['plan_id']
        success_url = serializer.validated_data['success_url']
        cancel_url = serializer.validated_data['cancel_url']
        
        user = request.user
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)

        # Get or create Stripe Customer ID for the user
        stripe_customer_id = user.profile.stripe_customer_id if hasattr(user, 'profile') and user.profile.stripe_customer_id else None
        
        if not stripe_customer_id:
            try:
                customer = stripe.Customer.create(
                    email=user.email,
                    name=user.full_name or user.username,
                    metadata={'uplas_user_id': str(user.id)}
                )
                stripe_customer_id = customer.id
                # Save Stripe Customer ID to user's profile
                if hasattr(user, 'profile'): # Assuming UserProfile model from earlier
                    user.profile.stripe_customer_id = stripe_customer_id
                    user.profile.save(update_fields=['stripe_customer_id'])
                else: # If no separate profile, try to save on User model itself if field exists
                    user.stripe_customer_id = stripe_customer_id # Make sure this field exists on User model
                    user.save(update_fields=['stripe_customer_id'])

            except stripe.error.StripeError as e:
                return Response({'error': f'Failed to create Stripe customer: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Check if user has an existing active/trialing subscription to this plan or a higher tier one
        # This logic can be complex (upgrades, downgrades). For simplicity, basic check:
        existing_subscription = UserSubscription.objects.filter(
            user=user, status__in=['active', 'trialing']
        ).first()

        checkout_mode = 'subscription'
        line_items = [{'price': plan.stripe_price_id, 'quantity': 1}]
        subscription_data = {}

        if existing_subscription and existing_subscription.stripe_subscription_id:
            # This is an update/change of plan scenario.
            # For simplicity, Stripe Checkout can handle some of this, or use Stripe Billing Portal.
            # More robust: Use Stripe's subscription update API.
            # For Checkout, if changing plans, you might cancel the old one and start a new one,
            # or use Stripe's Proration feature if setting up the Checkout session appropriately.
            # Let's assume we're creating a new subscription, old one needs manual/webhook handling for cancellation if not done by Stripe.
            # A better way for upgrades/downgrades: use Stripe Billing Portal or direct API calls to update subscription.
            # For this example, we'll create a new one.
            # If you want to use Stripe's upgrade/downgrade preview & logic:
            # subscription_data = {
            # 'items': [{'id': existing_subscription.stripe_items_id_from_stripe, 'deleted': True}, # If you store item ID
            # {'price': plan.stripe_price_id}],
            # 'proration_behavior': 'create_prorations', # or 'none'
            # }
            # This is more for direct stripe.Subscription.modify.
            # With Checkout, if customer_id is passed, Stripe might offer to update existing.
            pass


        try:
            checkout_session = stripe.checkout.Session.create(
                customer=stripe_customer_id,
                payment_method_types=['card'], # Add other payment methods as needed
                line_items=line_items,
                mode=checkout_mode,
                success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}', # Pass session ID back
                cancel_url=cancel_url,
                # automatic_tax={'enabled': True}, # If using Stripe Tax
                # allow_promotion_codes=True, # If you use Stripe promotion codes
                metadata={
                    'uplas_user_id': str(user.id),
                    'uplas_plan_id': str(plan.id),
                },
                # If it's an update, Stripe might need subscription ID to update:
                # subscription=existing_subscription.stripe_subscription_id if existing_subscription else None, # This is not how checkout updates subs
            )
            
            # Optionally: Create a preliminary UserSubscription record with 'incomplete' status
            # UserSubscription.objects.update_or_create(
            #     user=user,
            #     defaults={
            #         'plan': plan,
            #         'stripe_customer_id': stripe_customer_id,
            #         'status': 'incomplete', # Will be updated by webhook
            #         'stripe_checkout_session_id': checkout_session.id # Store if needed
            #     }
            # )
            # This is good to track initiated checkouts.

            return Response({'checkout_url': checkout_session.url, 'session_id': checkout_session.id}, status=status.HTTP_200_OK)
        except stripe.error.StripeError as e:
            return Response({'error': f'Stripe error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({'error': f'An unexpected error occurred: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StripeWebhookView(APIView):
    """
    Handles incoming webhooks from Stripe to update subscription statuses,
    record transactions, etc.
    /api/payments/stripe-webhook/ - This endpoint MUST be publicly accessible.
    """
    permission_classes = [permissions.AllowAny] # Stripe needs to be able to hit this

    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        event = None

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e: # Invalid payload
            return Response({'error': 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e: # Invalid signature
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Webhook construction error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # Handle the event
        event_type = event['type']
        event_data = event['data']['object']

        print(f"Received Stripe webhook: {event_type}, Event ID: {event['id']}")

        # Ensure idempotency: check if we've processed this event ID before
        # This might involve storing processed event IDs in a temporary cache or DB table.
        # For now, we'll proceed assuming new event.

        try:
            with transaction.atomic(): # Wrap processing in a DB transaction
                if event_type == 'checkout.session.completed':
                    self._handle_checkout_session_completed(event_data)
                
                elif event_type == 'customer.subscription.created':
                    self._handle_subscription_updated_or_created(event_data, is_new=True)
                
                elif event_type == 'customer.subscription.updated':
                    self._handle_subscription_updated_or_created(event_data)

                elif event_type == 'customer.subscription.deleted': # Includes canceled at period end
                    self._handle_subscription_deleted(event_data)
                
                elif event_type == 'customer.subscription.trial_will_end':
                    # Send reminder email to user
                    pass # Implement reminder logic

                elif event_type == 'invoice.payment_succeeded':
                    self._handle_invoice_payment_succeeded(event_data)

                elif event_type == 'invoice.payment_failed':
                    self._handle_invoice_payment_failed(event_data)
                
                # ... handle other event types as needed:
                # - charge.succeeded, charge.failed, charge.refunded
                # - payment_intent.succeeded, payment_intent.payment_failed
                # - customer.updated (e.g. if payment method changes)
                else:
                    print(f'Unhandled Stripe event type: {event_type}')

        except Exception as e:
            # Log the error thoroughly
            print(f"Error processing webhook event {event['id']} ({event_type}): {str(e)}")
            # Return 500 so Stripe retries, but be careful not to cause infinite retries for non-transient errors.
            return Response({'error': 'Internal server error while processing webhook.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'status': 'success'}, status=status.HTTP_200_OK)

    def _get_user_from_stripe_customer_id(self, stripe_customer_id):
        # Attempt to find user by Stripe Customer ID on UserProfile or User model
        try:
            # Check UserProfile first if it exists and stores stripe_customer_id
            if hasattr(User, 'profile') and hasattr(User.profile, 'stripe_customer_id'):
                 user_profile = User.profile.get_object_for_this_type(stripe_customer_id=stripe_customer_id)
                 return user_profile.user
            # Fallback to User model if it stores stripe_customer_id directly
            return User.objects.get(stripe_customer_id=stripe_customer_id)
        except (User.DoesNotExist, User.profile.RelatedObjectDoesNotExist, User.profile.through.DoesNotExist, AttributeError): # Catch potential errors
             print(f"Could not find user for Stripe Customer ID: {stripe_customer_id}")
             return None


    def _handle_checkout_session_completed(self, session_data):
        stripe_customer_id = session_data.get('customer')
        stripe_subscription_id = session_data.get('subscription') # Present if mode=subscription
        client_reference_id = session_data.get('client_reference_id') # If you passed it (e.g., user_id)
        uplas_user_id_metadata = session_data.get('metadata', {}).get('uplas_user_id')
        uplas_plan_id_metadata = session_data.get('metadata', {}).get('uplas_plan_id')
        payment_status = session_data.get('payment_status') # e.g. 'paid'

        user = None
        if uplas_user_id_metadata:
            try:
                user = User.objects.get(id=uplas_user_id_metadata)
            except User.DoesNotExist:
                print(f"Checkout session completed for non-existent uplas_user_id: {uplas_user_id_metadata}")
                return # Or handle as an anomaly

        if not user and stripe_customer_id:
            user = self._get_user_from_stripe_customer_id(stripe_customer_id)
        
        if not user:
            print(f"Checkout session completed but could not map to Uplas user. Stripe Cust ID: {stripe_customer_id}, Metadata User ID: {uplas_user_id_metadata}")
            return

        if payment_status == 'paid' and stripe_subscription_id:
            # The subscription itself will be handled by customer.subscription.created/updated.
            # This event confirms the checkout session itself was successful.
            # You might create a preliminary Transaction record here if desired.
            print(f"Checkout session completed and paid for user {user.id}, subscription {stripe_subscription_id}")
            
            # Ensure Stripe Customer ID is saved on the user if not already
            if stripe_customer_id and (not user.profile.stripe_customer_id if hasattr(user, 'profile') else not user.stripe_customer_id):
                if hasattr(user, 'profile'):
                    user.profile.stripe_customer_id = stripe_customer_id
                    user.profile.save(update_fields=['stripe_customer_id'])
                else:
                    user.stripe_customer_id = stripe_customer_id
                    user.save(update_fields=['stripe_customer_id'])
        elif payment_status != 'paid':
             print(f"Checkout session completed for user {user.id} but not paid (status: {payment_status}). Stripe Sub ID: {stripe_subscription_id}")


    def _handle_subscription_updated_or_created(self, sub_data, is_new=False):
        stripe_subscription_id = sub_data['id']
        stripe_customer_id = sub_data['customer']
        status = sub_data['status'] # e.g., active, trialing, past_due, canceled
        current_period_start_ts = sub_data['current_period_start']
        current_period_end_ts = sub_data['current_period_end']
        cancel_at_period_end = sub_data['cancel_at_period_end']
        canceled_at_ts = sub_data.get('canceled_at') # Timestamp or null
        trial_start_ts = sub_data.get('trial_start')
        trial_end_ts = sub_data.get('trial_end')

        # Get the primary plan/price associated with this subscription
        # Stripe subscription items is a list, usually one item for simple subs.
        stripe_price_id = None
        if sub_data.get('items') and sub_data['items'].get('data'):
            for item in sub_data['items']['data']:
                if item.get('price'):
                    stripe_price_id = item['price']['id']
                    break # Take the first one for simplicity
        
        plan = None
        if stripe_price_id:
            try:
                plan = SubscriptionPlan.objects.get(stripe_price_id=stripe_price_id)
            except SubscriptionPlan.DoesNotExist:
                print(f"Warning: Stripe subscription {stripe_subscription_id} references unknown Stripe Price ID {stripe_price_id}")
                # Potentially create a placeholder plan or log for admin review

        user = self._get_user_from_stripe_customer_id(stripe_customer_id)
        if not user:
            print(f"Subscription update/create for unknown Stripe customer: {stripe_customer_id}")
            return
        
        user_sub, created = UserSubscription.objects.update_or_create(
            user=user, # Using user as the primary key for update_or_create here assumes OneToOne
            # If using ForeignKey from User to UserSubscription, use stripe_subscription_id for uniqueness:
            # stripe_subscription_id=stripe_subscription_id,
            defaults={
                'plan': plan,
                'stripe_subscription_id': stripe_subscription_id, # Ensure this is set if it's the lookup
                'stripe_customer_id': stripe_customer_id, # Good to keep it on the sub model too
                'status': status,
                'start_date': datetime.fromtimestamp(sub_data['start_date'], tz=timezone.utc) if is_new and not UserSubscription.objects.filter(stripe_subscription_id=stripe_subscription_id).exists() else UserSubscription.objects.filter(stripe_subscription_id=stripe_subscription_id).first().start_date if UserSubscription.objects.filter(stripe_subscription_id=stripe_subscription_id).exists() else datetime.fromtimestamp(sub_data['start_date'], tz=timezone.utc) , # Set on creation only
                'current_period_start': datetime.fromtimestamp(current_period_start_ts, tz=timezone.utc),
                'current_period_end': datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc),
                'cancel_at_period_end': cancel_at_period_end,
                'canceled_at': datetime.fromtimestamp(canceled_at_ts, tz=timezone.utc) if canceled_at_ts else None,
                'trial_start_date': datetime.fromtimestamp(trial_start_ts, tz=timezone.utc) if trial_start_ts else None,
                'trial_end_date': datetime.fromtimestamp(trial_end_ts, tz=timezone.utc) if trial_end_ts else None,
            }
        )
        if created and is_new: # Only set start_date if truly new in our DB and from a create event
            user_sub.start_date = datetime.fromtimestamp(sub_data['start_date'], tz=timezone.utc)
            user_sub.save(update_fields=['start_date'])

        print(f"User subscription {user_sub.id} for user {user.id} {'created' if created else 'updated'}. Status: {status}")
        # The user_sub.save() method will update user.is_premium_subscriber

    def _handle_subscription_deleted(self, sub_data):
        stripe_subscription_id = sub_data['id']
        try:
            user_sub = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)
            user_sub.status = 'canceled' # Or 'expired' depending on context
            user_sub.canceled_at = datetime.fromtimestamp(sub_data.get('canceled_at', timezone.now().timestamp()), tz=timezone.utc)
            user_sub.current_period_end = user_sub.canceled_at # Usually ends when canceled
            user_sub.save()
            print(f"User subscription {user_sub.id} for user {user_sub.user.id} canceled.")
        except UserSubscription.DoesNotExist:
            print(f"Received subscription.deleted for unknown Stripe subscription ID: {stripe_subscription_id}")

    def _handle_invoice_payment_succeeded(self, invoice_data):
        stripe_customer_id = invoice_data.get('customer')
        stripe_subscription_id = invoice_data.get('subscription')
        stripe_charge_id = invoice_data.get('charge') # Can be null if payment is from other sources like credit balance
        stripe_payment_intent_id = invoice_data.get('payment_intent')
        
        user = self._get_user_from_stripe_customer_id(stripe_customer_id)
        if not user:
            print(f"Invoice payment succeeded for unknown Stripe customer: {stripe_customer_id}")
            return

        user_sub = None
        if stripe_subscription_id:
            try:
                user_sub = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id, user=user)
            except UserSubscription.DoesNotExist:
                print(f"Invoice payment succeeded for subscription {stripe_subscription_id} not found for user {user.id}")
        
        Transaction.objects.create(
            user=user,
            user_subscription=user_sub,
            stripe_charge_id=stripe_charge_id or stripe_payment_intent_id,
            stripe_invoice_id=invoice_data['id'],
            transaction_type='subscription_renewal' if user_sub and not invoice_data.get('billing_reason') == 'subscription_create' else 'subscription_signup',
            status='succeeded',
            amount=invoice_data['amount_paid'] / 100.0, # Stripe amounts are in cents
            currency=invoice_data['currency'],
            payment_method_details=invoice_data.get('payment_settings', {}).get('payment_method_details') or {'card': {'brand': invoice_data.get('payment_settings',{}).get('card_brand'), 'last4': invoice_data.get('payment_settings',{}).get('card_last4')}},
            description=f"Payment for invoice {invoice_data['id']}",
            processed_at=datetime.fromtimestamp(invoice_data['status_transitions']['paid_at'], tz=timezone.utc) if invoice_data.get('status_transitions',{}).get('paid_at') else timezone.now()
        )
        print(f"Transaction recorded for successful payment of invoice {invoice_data['id']} for user {user.id}")

    def _handle_invoice_payment_failed(self, invoice_data):
        stripe_customer_id = invoice_data.get('customer')
        stripe_subscription_id = invoice_data.get('subscription')
        user = self._get_user_from_stripe_customer_id(stripe_customer_id)
        if not user:
            print(f"Invoice payment failed for unknown Stripe customer: {stripe_customer_id}")
            return

        user_sub = None
        if stripe_subscription_id:
            try:
                user_sub = UserSubscription.objects.get(stripe_subscription_id=stripe_subscription_id, user=user)
                # Subscription status might be updated via customer.subscription.updated (e.g., to 'past_due')
            except UserSubscription.DoesNotExist:
                 print(f"Invoice payment failed for subscription {stripe_subscription_id} not found for user {user.id}")
        
        charge_error = invoice_data.get('last_finalization_error') or {}
        Transaction.objects.create(
            user=user,
            user_subscription=user_sub,
            stripe_charge_id=invoice_data.get('charge') or invoice_data.get('payment_intent'),
            stripe_invoice_id=invoice_data['id'],
            transaction_type='subscription_renewal' if user_sub else 'other_payment', # Adjust type
            status='failed',
            amount=invoice_data['amount_due'] / 100.0,
            currency=invoice_data['currency'],
            description=f"Failed payment for invoice {invoice_data['id']}",
            error_message=charge_error.get('message', 'Unknown payment failure.'),
            processed_at=timezone.now() # Time of failure processing by webhook
        )
        print(f"Transaction recorded for failed payment of invoice {invoice_data['id']} for user {user.id}")
        # Optionally, send notification to user about payment failure.
