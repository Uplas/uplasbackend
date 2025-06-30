
# apps/payments/views.py
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
import stripe

from .models import SubscriptionPlan, UserSubscription, PaymentTransaction
from .serializers import SubscriptionPlanSerializer, UserSubscriptionSerializer, PaymentTransactionSerializer, CreateSubscriptionSerializer, CancelSubscriptionSerializer
from apps.users.models import User # CORRECTED IMPORT

stripe.api_key = settings.STRIPE_SECRET_KEY

class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lists available subscription plans.
    """
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [AllowAny]

class UserSubscriptionViewSet(viewsets.ModelViewSet):
    """
    Manages user subscriptions.
    """
    serializer_class = UserSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserSubscription.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'], url_path='my-subscription')
    def my_subscription(self, request):
        try:
            subscription = UserSubscription.objects.get(user=request.user)
            serializer = self.get_serializer(subscription)
            return Response(serializer.data)
        except UserSubscription.DoesNotExist:
            return Response({'detail': 'No active subscription found.'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path='create-subscription')
    def create_subscription(self, request):
        serializer = CreateSubscriptionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        # Placeholder for Stripe creation logic
        return Response({'detail': 'Subscription creation endpoint not fully implemented.'}, status=status.HTTP_501_NOT_IMPLEMENTED)

    @action(detail=True, methods=['post'], url_path='cancel-subscription')
    def cancel_subscription(self, request, pk=None):
        serializer = CancelSubscriptionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        # Placeholder for Stripe cancellation logic
        return Response({'detail': 'Subscription cancellation endpoint not fully implemented.'}, status=status.HTTP_501_NOT_IMPLEMENTED)

class PaymentTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lists payment transactions for the authenticated user.
    """
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentTransaction.objects.filter(user=self.request.user)

class StripeWebhookAPIView(APIView):
    """
    Handles webhooks from Stripe.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
        
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except ValueError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # Handle the event
        if event['type'] == 'invoice.payment_succeeded':
            # Handle successful payment logic
            pass
        elif event['type'] == 'customer.subscription.deleted':
            # Handle subscription cancellation
            pass
        
        return Response(status=status.HTTP_200_OK)