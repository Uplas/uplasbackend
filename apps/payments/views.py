import stripe # Stripe Python library
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import transaction # For atomic operations

from rest_framework import viewsets, status, generics, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser

from .models import (
    SubscriptionPlan,
    UserSubscription,
    PaymentTransaction
)
from .serializers import (
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
    CreateSubscriptionSerializer,
    CancelSubscriptionSerializer,
    PaymentTransactionSerializer,
    StripeWebhookEventSerializer # For initial validation of webhook payload
)
from .permissions import (
    IsSubscriptionOwner,
    IsPaymentTransactionOwner,
    CanManageSubscription
)

# Initialize Stripe API with your secret key
stripe.api_key = settings.STRIPE_SECRET_KEY


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint to list and retrieve available subscription plans.
    Management (create, update, delete) of plans is typically done via Django admin
    or a separate admin-only API if needed, as these are critical and less frequently changed.
    If admin API management is needed, change to ModelViewSet and add IsAdminUser permission.
    """
    queryset = SubscriptionPlan.objects.filter(is_active=True).order_by('display_order', 'price')
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [AllowAny] # Anyone can see available plans
    lookup_field = 'id' # Or 'slug' if you add a slug field


class UserSubscriptionViewSet(viewsets.GenericViewSet): # Not a full ModelViewSet
    """
    API endpoint for users to manage their subscription.
    - Retrieve current subscription.
    - Create a new subscription (initiates Stripe Checkout or PaymentIntent flow).
    - Cancel a subscription.
    """
    serializer_class = UserSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Users can only see their own subscription.
        return UserSubscription.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'], url_path='my-subscription', url_name='my-subscription')
    def get_my_subscription(self, request):
        """
        Retrieves the current authenticated user's active subscription.
        """
        try:
            subscription = UserSubscription.objects.select_related('plan').get(user=request.user)
            # Could add logic here to refresh from Stripe if needed, or rely on webhooks
            serializer = self.get_serializer(subscription)
            return Response(serializer.data)
        except UserSubscription.DoesNotExist:
            return Response({'detail': _('No active subscription found.')}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path='create-subscription', url_name='create-subscription',
            serializer_class=CreateSubscriptionSerializer)
    def create_subscription(self, request):
        """
        Creates a new Stripe subscription for the user.
        Expects 'plan_id' and 'payment_method_id' (from Stripe Elements on frontend).
        This is one way to handle subscriptions (PaymentIntents with SetupIntents).
        Another way is Stripe Checkout.
        """
        serializer = CreateSubscriptionSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        plan = serializer.validated_data['plan_id'] # This is the plan object from validation
        payment_method_id = serializer.validated_data['payment_method_id']
        user = request.user

        # Check if user already has an active subscription (if only one is allowed)
        if UserSubscription.objects.filter(user=user, status__in=['active', 'trialing', 'past_due']).exists():
            return Response({'detail': _('You already have an active subscription.')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. Get or create a Stripe Customer for this user
            stripe_customer_id = None
            if hasattr(user, 'userprofile') and user.userprofile.stripe_customer_id: # Assuming stripe_customer_id on UserProfile
                stripe_customer_id = user.userprofile.stripe_customer_id
            
            if not stripe_customer_id:
                customer = stripe.Customer.create(
                    email=user.email,
                    name=user.full_name or user.username, # Ensure your User model has full_name
                    payment_method=payment_method_id,
                    invoice_settings={'default_payment_method': payment_method_id},
                    metadata={'django_user_id': str(user.id)}
                )
                stripe_customer_id = customer.id
                # Save stripe_customer_id to your UserProfile model
                if hasattr(user, 'userprofile'):
                    user.userprofile.stripe_customer_id = stripe_customer_id
                    user.userprofile.save()
                else: # Fallback or error if UserProfile doesn't exist
                    print(f"Warning: User {user.id} does not have a UserProfile to save Stripe Customer ID.")

            else: # Customer exists, attach payment method
                stripe.PaymentMethod.attach(payment_method_id, customer=stripe_customer_id)
                stripe.Customer.modify(stripe_customer_id, invoice_settings={'default_payment_method': payment_method_id})


            # 2. Create the Stripe Subscription
            stripe_subscription = stripe.Subscription.create(
                customer=stripe_customer_id,
                items=[{'price': plan.stripe_price_id}],
                expand=['latest_invoice.payment_intent', 'pending_setup_intent'],
                # trial_period_days=plan.trial_days if plan.trial_days else None, # If your plan model has trial_days
                # payment_behavior='default_incomplete' if SCA is required
                # off_session=True, # If payment is off-session
            )

            # 3. Create UserSubscription record in your DB
            # Important: Most fields will be updated by webhooks (status, current_period_end, etc.)
            # This initial record is a placeholder.
            with transaction.atomic():
                user_sub, created = UserSubscription.objects.update_or_create(
                    user=user,
                    defaults={ # Use defaults to update if an inactive one exists
                        'plan': plan,
                        'stripe_subscription_id': stripe_subscription.id,
                        'stripe_customer_id': stripe_customer_id,
                        'status': stripe_subscription.status, # Initial status from Stripe
                        'current_period_start': timezone.datetime.fromtimestamp(stripe_subscription.current_period_start, tz=timezone.utc) if stripe_subscription.current_period_start else None,
                        'current_period_end': timezone.datetime.fromtimestamp(stripe_subscription.current_period_end, tz=timezone.utc) if stripe_subscription.current_period_end else None,
                        'trial_start': timezone.datetime.fromtimestamp(stripe_subscription.trial_start, tz=timezone.utc) if stripe_subscription.trial_start else None,
                        'trial_end': timezone.datetime.fromtimestamp(stripe_subscription.trial_end, tz=timezone.utc) if stripe_subscription.trial_end else None,
                    }
                )
            
            # Handle PaymentIntent if immediate payment is required and successful
            # Or if it requires action (e.g., 3D Secure)
            latest_invoice = stripe_subscription.latest_invoice
            payment_intent = latest_invoice.payment_intent if latest_invoice else None
            
            response_data = {
                'subscription_id': user_sub.id,
                'stripe_subscription_id': stripe_subscription.id,
                'status': stripe_subscription.status
            }

            if payment_intent:
                response_data['payment_intent_status'] = payment_intent.status
                if payment_intent.status == 'requires_action' or payment_intent.status == 'requires_payment_method':
                    response_data['payment_intent_client_secret'] = payment_intent.client_secret
                elif payment_intent.status == 'succeeded':
                    # Create a PaymentTransaction record here or wait for webhook
                    PaymentTransaction.objects.create(
                        user=user,
                        user_subscription=user_sub,
                        stripe_charge_id=payment_intent.id, # or payment_intent.latest_charge
                        stripe_invoice_id=latest_invoice.id if latest_invoice else None,
                        amount=Decimal(payment_intent.amount_received) / 100, # Amount is in cents
                        currency=payment_intent.currency.upper(),
                        status='succeeded',
                        paid_at=timezone.datetime.fromtimestamp(payment_intent.created, tz=timezone.utc),
                        description=f"Subscription to {plan.name}"
                    )
            elif stripe_subscription.pending_setup_intent: # For trials or free plans that need PM for future
                 response_data['setup_intent_client_secret'] = stripe_subscription.pending_setup_intent.client_secret


            return Response(response_data, status=status.HTTP_201_CREATED)

        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Log the exception e
            return Response({'error': _('An unexpected error occurred. Please try again.')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @action(detail=False, methods=['post'], url_path='cancel-subscription', url_name='cancel-subscription',
            serializer_class=CancelSubscriptionSerializer, permission_classes=[IsAuthenticated, CanManageSubscription])
    def cancel_subscription(self, request):
        """
        Cancels the current authenticated user's active subscription.
        """
        serializer = CancelSubscriptionSerializer(data=request.data) # Validate if any params are passed
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        cancel_immediately = serializer.validated_data.get('cancel_immediately', False)

        try:
            user_subscription = UserSubscription.objects.get(user=request.user)
            # Check object permission (CanManageSubscription will use this object)
            self.check_object_permissions(request, user_subscription)

            if not user_subscription.stripe_subscription_id:
                return Response({'detail': _('Stripe subscription ID not found.')}, status=status.HTTP_400_BAD_REQUEST)

            if user_subscription.status == 'cancelled':
                 return Response({'detail': _('Subscription is already cancelled.')}, status=status.HTTP_400_BAD_REQUEST)

            if cancel_immediately:
                stripe.Subscription.delete(user_subscription.stripe_subscription_id)
                # Webhook 'customer.subscription.deleted' will update local status
            else: # Cancel at period end
                stripe.Subscription.modify(
                    user_subscription.stripe_subscription_id,
                    cancel_at_period_end=True
                )
                user_subscription.cancel_at_period_end = True
                user_subscription.status = 'pending_cancellation' # Local status update
                user_subscription.save()
                # Webhook 'customer.subscription.updated' will confirm cancel_at_period_end

            return Response({'detail': _('Subscription cancellation requested successfully.')}, status=status.HTTP_200_OK)

        except UserSubscription.DoesNotExist:
            return Response({'detail': _('No active subscription found to cancel.')}, status=status.HTTP_404_NOT_FOUND)
        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Log e
            return Response({'error': _('An unexpected error occurred.')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # TODO: Add endpoint for updating payment method (Stripe Billing Portal or custom flow)
    # @action(detail=False, methods=['post'], url_path='create-billing-portal-session', url_name='create-billing-portal')
    # def create_billing_portal_session(self, request):
    #     try:
    #         user_subscription = UserSubscription.objects.get(user=request.user)
    #         if not user_subscription.stripe_customer_id:
    #             return Response(...)
    #
    #         return_url = settings.STRIPE_BILLING_PORTAL_RETURN_URL # Configure in settings
    #         session = stripe.billing_portal.Session.create(
    #             customer=user_subscription.stripe_customer_id,
    #             return_url=return_url,
    #         )
    #         return Response({'url': session.url})
    #     except ...


class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for users to view their payment transaction history.
    """
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Users can only see their own payment transactions.
        return PaymentTransaction.objects.filter(user=self.request.user).order_by('-created_at')
    
    # No create/update/delete for users, these are system-generated via webhooks.


class StripeWebhookView(views.APIView):
    """
    Handles incoming webhooks from Stripe.
    This endpoint should not require CSRF protection or authentication from Stripe.
    Stripe authenticates webhooks using signatures.
    """
    permission_classes = [AllowAny] # Stripe does not send auth headers

    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET # Your webhook signing secret

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        except ValueError as e:
            # Invalid payload
            return Response({'error': 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Validate event structure (optional, but good practice)
        event_serializer = StripeWebhookEventSerializer(data=event)
        if not event_serializer.is_valid():
            # Log this error, as it means Stripe sent something unexpected
            print(f"Stripe Webhook Deserialization Error: {event_serializer.errors}")
            # Still try to process if possible, or return 400 if strict
            # return Response(event_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            pass


        # Handle the event
        event_type = event['type']
        data_object = event['data']['object'] # The Stripe object related to the event

        print(f"Received Stripe event: {event_type}, Event ID: {event.id}")

        try:
            with transaction.atomic(): # Ensure database operations are atomic for each event
                if event_type == 'checkout.session.completed':
                    # This event is used if you are using Stripe Checkout for one-time payments or subscriptions
                    # session = data_object
                    # client_reference_id = session.get('client_reference_id') # Your internal user ID
                    # stripe_customer_id = session.get('customer')
                    # stripe_subscription_id = session.get('subscription') # If it's a subscription checkout
                    # payment_intent_id = session.get('payment_intent')
                    #
                    # user = User.objects.filter(id=client_reference_id).first()
                    # if not user: # Or handle error
                    #     print(f"Webhook Error: User not found for client_reference_id {client_reference_id}")
                    #     return Response({'status': 'error', 'message': 'User not found'}, status=status.HTTP_400_BAD_REQUEST)
                    #
                    # if stripe_subscription_id: # It's a subscription
                    #     # Retrieve the subscription from Stripe to get full details (like plan)
                    #     stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
                    #     plan_stripe_price_id = stripe_sub.items.data[0].price.id
                    #     plan = SubscriptionPlan.objects.filter(stripe_price_id=plan_stripe_price_id).first()
                    #
                    #     if not plan:
                    #         print(f"Webhook Error: Plan not found for Stripe Price ID {plan_stripe_price_id}")
                    #         return Response({'status': 'error', 'message': 'Plan not found'}, status=status.HTTP_400_BAD_REQUEST)
                    #
                    #     UserSubscription.objects.update_or_create(
                    #         stripe_subscription_id=stripe_subscription_id,
                    #         defaults={
                    #             'user': user,
                    #             'plan': plan,
                    #             'stripe_customer_id': stripe_customer_id,
                    #             'status': stripe_sub.status,
                    #             'current_period_start': timezone.datetime.fromtimestamp(stripe_sub.current_period_start, tz=timezone.utc),
                    #             'current_period_end': timezone.datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc),
                    #             'trial_start': timezone.datetime.fromtimestamp(stripe_sub.trial_start, tz=timezone.utc) if stripe_sub.trial_start else None,
                    #             'trial_end': timezone.datetime.fromtimestamp(stripe_sub.trial_end, tz=timezone.utc) if stripe_sub.trial_end else None,
                    #         }
                    #     )
                    #     print(f"Subscription created/updated for user {user.id} via checkout.")
                    #
                    # # Handle payment intent if present (for one-time or first subscription payment)
                    # if payment_intent_id:
                    #     pi = stripe.PaymentIntent.retrieve(payment_intent_id)
                    #     if pi.status == 'succeeded':
                    #         # Create PaymentTransaction
                    #         PaymentTransaction.objects.update_or_create(
                    #             stripe_charge_id=pi.id, # Using PI id as charge id
                    #             defaults={
                    #                 'user':user,
                    #                 'user_subscription': UserSubscription.objects.filter(stripe_subscription_id=stripe_subscription_id).first() if stripe_subscription_id else None,
                    #                 'amount': Decimal(pi.amount_received) / 100,
                    #                 'currency': pi.currency.upper(),
                    #                 'status': 'succeeded',
                    #                 'paid_at': timezone.datetime.fromtimestamp(pi.created, tz=timezone.utc),
                    #                 'description': session.get('metadata', {}).get('description', f"Payment via Checkout Session {session.id}")
                    #             }
                    #         )
                    #         print(f"PaymentTransaction created for PI {pi.id}")
                    pass # Implement based on your Stripe Checkout setup

                elif event_type == 'invoice.payment_succeeded':
                    invoice = data_object
                    stripe_subscription_id = invoice.get('subscription')
                    stripe_customer_id = invoice.get('customer')
                    
                    user_sub = UserSubscription.objects.filter(stripe_subscription_id=stripe_subscription_id).first()
                    user = User.objects.filter(userprofile__stripe_customer_id=stripe_customer_id).first() # Assumes stripe_customer_id on UserProfile
                    if not user_sub and user: # Try to find by user if sub not yet created by that ID
                        user_sub = UserSubscription.objects.filter(user=user).first()


                    if user_sub:
                        # Update subscription period
                        user_sub.status = 'active' # Or map from invoice.subscription.status
                        user_sub.current_period_start = timezone.datetime.fromtimestamp(invoice.period_start, tz=timezone.utc)
                        user_sub.current_period_end = timezone.datetime.fromtimestamp(invoice.period_end, tz=timezone.utc)
                        user_sub.save()

                        # Create PaymentTransaction
                        PaymentTransaction.objects.update_or_create(
                            stripe_charge_id=invoice.payment_intent or invoice.charge, # Use PI if available, else charge
                            stripe_invoice_id=invoice.id,
                            defaults={
                                'user': user_sub.user,
                                'user_subscription': user_sub,
                                'amount': Decimal(invoice.amount_paid) / 100,
                                'currency': invoice.currency.upper(),
                                'status': 'succeeded',
                                'paid_at': timezone.datetime.fromtimestamp(invoice.status_transitions.paid_at, tz=timezone.utc) if invoice.status_transitions.paid_at else timezone.now(),
                                'description': f"Invoice paid: {invoice.number or invoice.id}",
                                'payment_method_details': {'type': invoice.payment_settings.payment_method_types[0] if invoice.payment_settings.payment_method_types else 'unknown'}
                            }
                        )
                        print(f"Invoice payment succeeded for subscription {stripe_subscription_id}")
                    else:
                        print(f"Webhook Warning: UserSubscription not found for stripe_subscription_id {stripe_subscription_id} or customer {stripe_customer_id} during invoice.payment_succeeded.")


                elif event_type == 'invoice.payment_failed':
                    invoice = data_object
                    stripe_subscription_id = invoice.get('subscription')
                    user_sub = UserSubscription.objects.filter(stripe_subscription_id=stripe_subscription_id).first()
                    if user_sub:
                        user_sub.status = 'past_due' # Or based on Stripe's recommended status
                        user_sub.save()
                        # Create/Update PaymentTransaction to 'failed'
                        PaymentTransaction.objects.update_or_create(
                            stripe_charge_id=invoice.payment_intent or invoice.charge or f"failed_inv_{invoice.id}", # Ensure a unique ID
                            stripe_invoice_id=invoice.id,
                            defaults={
                                'user':user_sub.user,
                                'user_subscription': user_sub,
                                'amount': Decimal(invoice.amount_due) / 100,
                                'currency': invoice.currency.upper(),
                                'status': 'failed',
                                'description': f"Invoice payment failed: {invoice.number or invoice.id}. Reason: {invoice.last_finalization_error.message if invoice.last_finalization_error else 'Unknown'}",
                            }
                        )
                        print(f"Invoice payment failed for subscription {stripe_subscription_id}")
                        # TODO: Notify user about payment failure

                elif event_type == 'customer.subscription.updated':
                    stripe_sub = data_object
                    user_sub = UserSubscription.objects.filter(stripe_subscription_id=stripe_sub.id).first()
                    if user_sub:
                        user_sub.status = stripe_sub.status
                        user_sub.current_period_start = timezone.datetime.fromtimestamp(stripe_sub.current_period_start, tz=timezone.utc)
                        user_sub.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc)
                        user_sub.cancel_at_period_end = stripe_sub.cancel_at_period_end
                        if stripe_sub.canceled_at:
                            user_sub.cancelled_at = timezone.datetime.fromtimestamp(stripe_sub.canceled_at, tz=timezone.utc)
                            user_sub.status = 'cancelled' # Ensure final status
                        
                        # Update plan if changed (e.g. upgrade/downgrade)
                        new_stripe_price_id = stripe_sub.items.data[0].price.id
                        if user_sub.plan.stripe_price_id != new_stripe_price_id:
                            new_plan = SubscriptionPlan.objects.filter(stripe_price_id=new_stripe_price_id).first()
                            if new_plan:
                                user_sub.plan = new_plan
                            else:
                                print(f"Webhook Warning: New plan with Stripe Price ID {new_stripe_price_id} not found in DB.")
                        
                        user_sub.save()
                        print(f"Subscription {stripe_sub.id} updated. Status: {user_sub.status}")

                elif event_type == 'customer.subscription.deleted': # Or .canceled
                    stripe_sub = data_object
                    user_sub = UserSubscription.objects.filter(stripe_subscription_id=stripe_sub.id).first()
                    if user_sub:
                        user_sub.status = 'cancelled'
                        user_sub.cancelled_at = timezone.datetime.fromtimestamp(stripe_sub.canceled_at, tz=timezone.utc) if stripe_sub.canceled_at else timezone.now()
                        user_sub.current_period_end = user_sub.cancelled_at # Ensure period end reflects cancellation
                        user_sub.save()
                        print(f"Subscription {stripe_sub.id} deleted/cancelled.")
                
                elif event_type == 'customer.subscription.trial_will_end':
                    # Send reminder to user
                    print(f"Subscription trial ending soon for {data_object.id}")
                    pass

                # Add more event handlers as needed:
                # - payment_intent.succeeded, payment_intent.payment_failed
                # - customer.updated (e.g., default payment method changed)
                # - etc.

                else:
                    print(f'Unhandled event type {event_type}')

        except User.DoesNotExist: # Or UserProfile.DoesNotExist
            print(f"Webhook Error: User or UserProfile not found for Stripe Customer ID {data_object.get('customer')}")
            # It's important not to crash the webhook handler, so log and return 200 if possible,
            # or 400 if it's a clear data issue that Stripe shouldn't retry.
            return Response({'status': 'error', 'message': 'User mapping issue'}, status=status.HTTP_400_BAD_REQUEST)
        except UserSubscription.DoesNotExist:
            print(f"Webhook Error: UserSubscription not found for Stripe Subscription ID {data_object.get('id') or data_object.get('subscription')}")
            return Response({'status': 'error', 'message': 'Subscription mapping issue'}, status=status.HTTP_400_BAD_REQUEST)
        except SubscriptionPlan.DoesNotExist:
            print(f"Webhook Error: SubscriptionPlan not found for Stripe Price ID {data_object.get('items', {}).get('data', [{}])[0].get('price', {}).get('id')}")
            return Response({'status': 'error', 'message': 'Plan mapping issue'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Log the exception for debugging
            print(f"Webhook processing error: {str(e)}")
            # Return 500 to signal Stripe to retry (for transient errors)
            # or 400 if it's a permanent issue with the event data.
            return Response({'error': 'Webhook processing error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


        return Response({'status': 'success'}, status=status.HTTP_200_OK)
