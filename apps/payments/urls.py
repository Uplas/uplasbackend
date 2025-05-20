from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SubscriptionPlanViewSet, UserSubscriptionViewSet, TransactionViewSet,
    CreateCheckoutSessionView, StripeWebhookView
)

router = DefaultRouter()
router.register(r'plans', SubscriptionPlanViewSet, basename='subscriptionplan')
router.register(r'subscriptions', UserSubscriptionViewSet, basename='usersubscription') # For user's own sub
router.register(r'transactions', TransactionViewSet, basename='transaction') # For user's own transactions

app_name = 'payments'

urlpatterns = [
    path('', include(router.urls)),
    path('create-checkout-session/', CreateCheckoutSessionView.as_view(), name='create-checkout-session'),
    path('stripe-webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
    # Potentially add an endpoint for Stripe Billing Portal session creation
    # path('create-billing-portal-session/', CreateBillingPortalSessionView.as_view(), name='create-billing-portal'),
]
