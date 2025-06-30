# apps/payments/models.py
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

# Assuming a shared base model for UUIDs and timestamps, like in other apps
from apps.core.models import BaseModel

# --- Choices ---
BILLING_CYCLE_CHOICES = [
    ('monthly', _('Monthly')),
    ('annually', _('Annually')),
    ('quarterly', _('Quarterly')),
]

SUBSCRIPTION_STATUS_CHOICES = [
    ('active', _('Active')),
    ('trialing', _('Trialing')),
    ('past_due', _('Past Due')),
    ('cancelled', _('Cancelled')),
    ('incomplete', _('Incomplete')),
    ('pending_cancellation', _('Pending Cancellation')),
]

PAYMENT_STATUS_CHOICES = [
    ('pending', _('Pending')),
    ('succeeded', _('Succeeded')),
    ('failed', _('Failed')),
    ('refunded', _('Refunded')),
]


# --- Models ---
class SubscriptionPlan(BaseModel):
    """
    Defines a subscription plan available for users (e.g., Basic, Premium).
    This model maps to a Stripe "Price" object.
    """
    name = models.CharField(max_length=150, unique=True, verbose_name=_('Plan Name'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))
    stripe_price_id = models.CharField(max_length=255, unique=True, verbose_name=_('Stripe Price ID'), help_text=_("The ID of the Price object in Stripe (e.g., price_xxxxxxxxxxxxxx)"))
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Price'))
    currency = models.CharField(max_length=3, choices=settings.CURRENCY_CHOICES, default='USD', verbose_name=_('Currency'))
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES, default='monthly', verbose_name=_('Billing Cycle'))
    features = models.JSONField(default=dict, blank=True, help_text=_("Key-value pairs of features for this plan."))
    is_active = models.BooleanField(default=True, verbose_name=_('Is Active'), help_text=_("Inactive plans are not offered to new subscribers."))
    display_order = models.PositiveIntegerField(default=0, help_text=_("Order for displaying plans, lower numbers first."))

    class Meta:
        verbose_name = _('Subscription Plan')
        verbose_name_plural = _('Subscription Plans')
        ordering = ['display_order', 'price']

    def __str__(self):
        return f"{self.name} ({self.price} {self.currency}/{self.billing_cycle})"


class UserSubscription(BaseModel):
    """
    Represents a user's subscription to a specific plan.
    This model maps to a Stripe "Subscription" object.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription', verbose_name=_('User'))
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, related_name='subscriptions', verbose_name=_('Plan'))
    stripe_subscription_id = models.CharField(max_length=255, unique=True, verbose_name=_('Stripe Subscription ID'))
    stripe_customer_id = models.CharField(max_length=255, verbose_name=_('Stripe Customer ID'))
    status = models.CharField(max_length=30, choices=SUBSCRIPTION_STATUS_CHOICES, default='incomplete', verbose_name=_('Status'))
    
    current_period_start = models.DateTimeField(null=True, blank=True, verbose_name=_('Current Period Start'))
    current_period_end = models.DateTimeField(null=True, blank=True, verbose_name=_('Current Period End'))
    cancel_at_period_end = models.BooleanField(default=False, verbose_name=_('Cancel at Period End'))
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Cancelled At'))
    
    trial_start = models.DateTimeField(null=True, blank=True, verbose_name=_('Trial Start'))
    trial_end = models.DateTimeField(null=True, blank=True, verbose_name=_('Trial End'))
    
    metadata = models.JSONField(default=dict, blank=True, help_text=_("Metadata from Stripe."))

    class Meta:
        verbose_name = _('User Subscription')
        verbose_name_plural = _('User Subscriptions')

    def __str__(self):
        return f"{self.user.email}'s subscription to {self.plan.name if self.plan else 'N/A'}"

    @property
    def is_active(self):
        """Checks if the subscription is currently active and within the valid period."""
        from django.utils import timezone
        return self.status == 'active' and self.current_period_end is not None and self.current_period_end > timezone.now()

    @property
    def is_trialing(self):
        """Checks if the subscription is in a trial period."""
        from django.utils import timezone
        return self.status == 'trialing' and self.trial_end is not None and self.trial_end > timezone.now()


class PaymentTransaction(BaseModel):
    """
    Logs every payment transaction, successful or failed.
    This model maps to a Stripe "Charge" or "PaymentIntent" object.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='payment_transactions', verbose_name=_('User'))
    user_subscription = models.ForeignKey(UserSubscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_transactions', verbose_name=_('Associated Subscription'))
    stripe_charge_id = models.CharField(max_length=255, unique=True, verbose_name=_('Stripe Charge/PaymentIntent ID'))
    stripe_invoice_id = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name=_('Stripe Invoice ID'))
    
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Amount'))
    currency = models.CharField(max_length=3, choices=settings.CURRENCY_CHOICES, default='USD', verbose_name=_('Currency'))
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending', verbose_name=_('Status'))
    
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Paid At'))
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Description'))
    
    payment_method_details = models.JSONField(default=dict, blank=True, help_text=_("Details about the payment method used, e.g., card brand, last4."))
    stripe_event_data = models.JSONField(default=dict, blank=True, help_text=_("Raw Stripe event data for reference."))

    class Meta:
        verbose_name = _('Payment Transaction')
        verbose_name_plural = _('Payment Transactions')
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment {self.id} by {self.user.email} - {self.amount} {self.currency} ({self.get_status_display()})"