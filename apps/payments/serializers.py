from rest_framework import serializers
from .models import SubscriptionPlan, UserSubscription, Transaction
from apps.users.serializers import UserSerializer # Potentially for user details in transaction

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'tier_level', 'slug', 'description', 'price', 'currency',
            'billing_interval', 'features', 'display_order', 'is_active',
            'stripe_price_id' # Important for frontend to initiate checkout
        ]
        read_only_fields = ['id', 'slug', 'is_active'] # stripe_price_id is usually set by admin

class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    user = UserSerializer(read_only=True, fields=['id', 'username', 'email']) # Basic user info

    class Meta:
        model = UserSubscription
        fields = [
            'id', 'user', 'plan', 'stripe_subscription_id', 'stripe_customer_id',
            'status', 'start_date', 'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'canceled_at', 'trial_start_date', 'trial_end_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields # Most fields are managed by backend/webhooks

class TransactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True, fields=['id', 'username']) # Basic user info
    user_subscription = UserSubscriptionSerializer(read_only=True, fields=['id', 'plan', 'status']) # Basic subscription info

    class Meta:
        model = Transaction
        fields = [
            'id', 'user', 'user_subscription', 'stripe_charge_id', 'stripe_invoice_id',
            'transaction_type', 'status', 'amount', 'currency',
            'payment_method_details', 'description', 'error_message',
            'created_at', 'processed_at'
        ]
        read_only_fields = fields # Transactions are records of events

# Serializers for creating subscriptions / handling payments
class CreateSubscriptionCheckoutSessionSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField(required=True)
    success_url = serializers.URLField(required=True, help_text="URL to redirect to on successful payment.")
    cancel_url = serializers.URLField(required=True, help_text="URL to redirect to on payment cancellation.")

    def validate_plan_id(self, value):
        try:
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
            if not plan.stripe_price_id:
                raise serializers.ValidationError("This plan is not configured for online payment (missing Stripe Price ID).")
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive subscription plan ID.")
        return value

class StripeWebhookEventSerializer(serializers.Serializer):
    # This is a very basic serializer for logging/initial validation.
    # Actual event parsing will use the Stripe library.
    id = serializers.CharField()
    type = serializers.CharField()
    # data = serializers.JSONField() # The 'data' object from Stripe event
    # api_version = serializers.CharField(required=False)
    # created = serializers.IntegerField(required=False)
    # ... other common Stripe event fields
