from rest_framework import serializers
from django.conf import settings # For settings.AUTH_USER_MODEL
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .models import SubscriptionPlan, UserSubscription, Transaction

# Assuming BasicUserSerializer is available for embedding user details.
# If not, define a minimal one or import from users.serializers.
# from apps.users.serializers import BasicUserSerializer
# For testing or if BasicUserSerializer is not yet robustly defined in users app:
class BasicUserSerializerForPayments(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'email', 'full_name'] # Essential fields for display
        read_only_fields = fields

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    # billing_interval_display = serializers.CharField(source='get_billing_interval_display', read_only=True)
    # tier_level_display = serializers.CharField(source='get_tier_level_display', read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'tier_level', #'tier_level_display',
            'slug', 'description', 'price', 'currency',
            'billing_interval', #'billing_interval_display',
            'features', 'display_order', 'is_active',
            'stripe_price_id' # Crucial for frontend to initiate Stripe Checkout
        ]
        read_only_fields = ['id', 'slug', 'is_active'] # stripe_price_id typically admin-set

class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True) # Nested plan details
    user = BasicUserSerializerForPayments(read_only=True) # Basic user details
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_currently_active = serializers.BooleanField(read_only=True) # From model property

    class Meta:
        model = UserSubscription
        fields = [
            'id', 'user', 'plan', 'stripe_subscription_id', 'stripe_customer_id',
            'status', 'status_display', 'is_currently_active',
            'start_date', 'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'canceled_at', 'ended_at',
            'trial_start_date', 'trial_end_date',
            'created_at', 'updated_at'
        ]
        # Most fields are managed by backend logic (Stripe webhooks), so primarily read-only from API user perspective.
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    user = BasicUserSerializerForPayments(read_only=True)
    # Optionally, nest basic subscription info if relevant for transaction display
    # class NestedSubscriptionSerializer(serializers.ModelSerializer):
    #     plan_name = serializers.CharField(source='plan.name', read_only=True,allow_null=True)
    #     class Meta:
    #         model = UserSubscription
    #         fields = ['id', 'plan_name', 'status']
    # user_subscription = NestedSubscriptionSerializer(read_only=True)
    
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'user', 'user_subscription', # Consider if full UserSubscriptionSerializer is too much here
            'stripe_payment_intent_id', 'stripe_charge_id', 'stripe_invoice_id',
            'transaction_type', 'transaction_type_display',
            'status', 'status_display',
            'amount', 'currency',
            'payment_method_details', 'description', 'error_message',
            'created_at', 'processed_at' # Our record creation time and Stripe event time
        ]
        read_only_fields = fields # Transactions are records of events, not directly mutable by API users


class CreateSubscriptionCheckoutSessionSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField(required=True)
    success_url = serializers.URLField(required=True, max_length=2000, help_text="URL to redirect to on successful payment.")
    cancel_url = serializers.URLField(required=True, max_length=2000, help_text="URL to redirect to on payment cancellation.")

    def validate_plan_id(self, value):
        try:
            # Ensure the plan is active and has a Stripe Price ID
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
            if not plan.stripe_price_id:
                raise serializers.ValidationError(
                    _("This subscription plan is not configured for online payment. Missing Stripe Price ID.")
                )
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError(_("Invalid or inactive subscription plan ID."))
        return value # Return the validated plan ID (UUID)

# This serializer is more for conceptual understanding of webhook data structure.
# The actual parsing in the view will use stripe.Webhook.construct_event() which returns a StripeObject.
class StripeWebhookEventDataSerializer(serializers.Serializer): # Example, not directly used for validation in view
    id = serializers.CharField(read_only=True)
    object = serializers.CharField(read_only=True)
    # ... other common fields in event_data['object']
    # This would vary greatly depending on the event type.

class StripeWebhookEventSerializer(serializers.Serializer): # Conceptual
    id = serializers.CharField(read_only=True) # Stripe Event ID
    type = serializers.CharField(read_only=True) # e.g., 'checkout.session.completed'
    # data = StripeWebhookEventDataSerializer(read_only=True) # The event data object
    # api_version = serializers.CharField(read_only=True, required=False)
    # created = serializers.IntegerField(read_only=True, required=False) # Timestamp

    # This serializer is not strictly used for validation in the webhook view because
    # Stripe's library handles the construction and gives a StripeObject.
    # It's more for documenting the expected high-level structure if you were to log raw events.
