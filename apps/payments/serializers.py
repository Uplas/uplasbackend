from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.conf import settings

from .models import (
    SubscriptionPlan,
    UserSubscription,
    PaymentTransaction,
    BILLING_CYCLE_CHOICES,
    PAYMENT_STATUS_CHOICES,
    SUBSCRIPTION_STATUS_CHOICES
)

User = get_user_model()

# --- Simple Serializer for User (if needed for nesting) ---
class SimpleUserSerializer(serializers.ModelSerializer):
    """
    A simple serializer for basic user information.
    """
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name'] # Adjust as per your User model

# --- Subscription Plan Serializers ---
class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Serializer for SubscriptionPlan model.
    - Admins can create/update all fields.
    - General users can typically only read.
    """
    currency_display = serializers.CharField(source='get_currency_display', read_only=True)
    billing_cycle_display = serializers.CharField(source='get_billing_cycle_display', read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'name', 'description', 'stripe_price_id',
            'price', 'currency', 'currency_display',
            'billing_cycle', 'billing_cycle_display', 'features',
            'is_active', 'display_order',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'currency_display', 'billing_cycle_display']
        # For admin interface, all fields might be writable.
        # For general API, stripe_price_id might be read_only after creation.

    def validate_stripe_price_id(self, value):
        if not value.startswith('price_'):
            raise serializers.ValidationError(_("Invalid Stripe Price ID format. It should start with 'price_'."))
        return value

# --- User Subscription Serializers ---
class UserSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for UserSubscription model.
    - User sees their own subscription.
    - Admin can see/manage all.
    """
    user = SimpleUserSerializer(read_only=True)
    plan = SubscriptionPlanSerializer(read_only=True) # Show plan details
    plan_id = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.filter(is_active=True),
        source='plan',
        write_only=True,
        label=_("Subscription Plan ID")
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_active_property = serializers.BooleanField(source='is_active', read_only=True) # From @property
    is_trialing_property = serializers.BooleanField(source='is_trialing', read_only=True) # From @property

    class Meta:
        model = UserSubscription
        fields = [
            'id', 'user', 'plan', 'plan_id',
            'stripe_subscription_id', 'stripe_customer_id',
            'status', 'status_display',
            'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'trial_start', 'trial_end',
            'metadata', 'created_at', 'updated_at', 'cancelled_at',
            'is_active_property', 'is_trialing_property'
        ]
        read_only_fields = [
            'id', 'user', 'plan', # Plan is set via plan_id on create
            'stripe_subscription_id', 'stripe_customer_id', # These are set by backend Stripe integration
            'status', 'status_display', # Status is managed by Stripe webhooks / backend logic
            'current_period_start', 'current_period_end',
            'trial_start', 'trial_end',
            'created_at', 'updated_at', 'cancelled_at',
            'is_active_property', 'is_trialing_property'
        ]
        # 'cancel_at_period_end' might be writable by the user to request cancellation.
        # 'plan_id' is write_only for creating/changing subscriptions.

    def validate(self, data):
        request = self.context.get('request')
        user = request.user if request else None

        if not self.instance: # Creating a new subscription
            if UserSubscription.objects.filter(user=user).exists():
                 # Depending on business logic: allow multiple (ForeignKey) or only one (OneToOneField)
                 # Current model is OneToOneField for user.
                raise serializers.ValidationError(_("User already has an active subscription."))
        return data

    # create() and update() methods will likely be handled in views that interact with Stripe
    # For example, creating a UserSubscription record AFTER a successful Stripe subscription.
    # Updating status, period_end etc., will be done via webhooks.

class CreateSubscriptionSerializer(serializers.Serializer):
    """
    Serializer for initiating a new subscription.
    Expects a plan_id and a Stripe PaymentMethod ID (pm_xxxx).
    """
    plan_id = serializers.UUIDField(help_text=_("The UUID of the SubscriptionPlan to subscribe to."))
    payment_method_id = serializers.CharField(
        max_length=100,
        write_only=True, # Only for input, not for display
        help_text=_("The Stripe PaymentMethod ID (e.g., pm_xxxxxxxxxxxxxx) obtained from Stripe Elements/SDK.")
    )
    # coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True, help_text=_("Optional coupon code."))


    def validate_plan_id(self, value):
        try:
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError(_("Invalid or inactive subscription plan ID."))
        return plan # Return the plan object for use in the view

    def validate_payment_method_id(self, value):
        if not value.startswith('pm_'):
            raise serializers.ValidationError(_("Invalid Stripe PaymentMethod ID format."))
        return value

class CancelSubscriptionSerializer(serializers.Serializer):
    """
    Serializer for requesting subscription cancellation.
    May not need any fields if it's just an action endpoint.
    Could include a reason for cancellation if desired.
    """
    cancel_immediately = serializers.BooleanField(
        default=False,
        required=False,
        help_text=_("If true, attempt to cancel immediately. Otherwise, cancel at period end.")
    )
    # reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


# --- Payment Transaction Serializers ---
class PaymentTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for PaymentTransaction model.
    Typically read-only for users, as transactions are created by the system (e.g., Stripe webhooks).
    """
    user = SimpleUserSerializer(read_only=True)
    user_subscription_id = serializers.UUIDField(source='user_subscription.id', read_only=True, allow_null=True)
    # course_purchased_title = serializers.CharField(source='course_purchased.title', read_only=True, allow_null=True) # If one-time course purchases
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    currency_display = serializers.CharField(source='get_currency_display', read_only=True)


    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'user', 'user_subscription_id', #'course_purchased_title',
            'stripe_charge_id', 'stripe_invoice_id',
            'amount', 'currency', 'currency_display',
            'status', 'status_display',
            'payment_method_details', 'description',
            'created_at', 'paid_at', 'updated_at'
        ]
        read_only_fields = fields # All fields are typically read-only from a user API perspective

# --- Stripe Webhook Event Serializers (Internal Use) ---
# These are not for user-facing APIs but for processing incoming webhooks from Stripe.

class StripeWebhookEventSerializer(serializers.Serializer):
    """
    Basic serializer to validate the structure of an incoming Stripe webhook event.
    Specific event types (e.g., invoice.payment_succeeded, customer.subscription.updated)
    will have their own data structures within event.data.object.
    """
    id = serializers.CharField() # Stripe Event ID (evt_xxxx)
    type = serializers.CharField() # e.g., 'invoice.payment_succeeded'
    api_version = serializers.CharField()
    created = serializers.IntegerField() # Unix timestamp
    data = serializers.JSONField() # Contains the actual Stripe object related to the event
    livemode = serializers.BooleanField()
    pending_webhooks = serializers.IntegerField()
    request = serializers.JSONField(allow_null=True) # Contains id and idempotency_key

    # You might add more validation or specific fields based on common event structures if needed.

