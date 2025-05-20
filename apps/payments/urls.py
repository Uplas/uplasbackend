from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SubscriptionPlanViewSet, UserSubscriptionViewSet, TransactionViewSet,
    CreateCheckoutSessionView, StripeWebhookView
)

router = DefaultRouter()
router.register(r'plans', SubscriptionPlanViewSet, basename='subscriptionplan')
# UserSubscriptionViewSet is for the current user's single subscription.
# No need to register with router if we only expose the list (detail of one) action.
# If we had /api/payments/subscriptions/{id}/ for admins, then register.
# For now, we'll map it directly for the current user.
router.register(r'transactions', TransactionViewSet, basename='transaction')

app_name = 'payments'

# Custom mapping for UserSubscription as it's a singular resource for the current user.
user_subscription_actions = UserSubscriptionViewSet.as_view({
    'get': 'list', # 'list' action in our view returns the single subscription or 404
    'post': 'cancel_my_subscription' # Custom action mapped via @action(detail=False)
})


urlpatterns = [
    path('', include(router.urls)),
    path('my-subscription/', user_subscription_actions, name='my-subscription-detail'), # GET for detail, POST for cancel
    path('create-checkout-session/', CreateCheckoutSessionView.as_view(), name='create-checkout-session'),
    path('stripe-webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
]
