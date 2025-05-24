import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

# Assuming your courses app has a Course model
# from apps.courses.models import Course # Uncomment if direct linking to Course is needed for one-time purchases

# Choices for Subscription Plan
BILLING_CYCLE_CHOICES = [
    ('monthly', _('Monthly')),
    ('quarterly', _('Quarterly')),
    ('annually', _('Annually')),
    # ('one_time', _('One-Time Purchase')), # If you have one-time course purchases vs subscriptions
]

# Choices for Payment Status
PAYMENT_STATUS_CHOICES = [
    ('pending', _('Pending')),
    ('succeeded', _('Succeeded')),
    ('failed', _('Failed')),
    ('refunded', _('Refunded')),
    ('requires_action', _('Requires Action')), # For SCA
]

# Choices for Subscription Status
SUBSCRIPTION_STATUS_CHOICES = [
    ('active', _('Active')),
    ('inactive', _('Inactive')), # Generic inactive state
    ('pending_cancellation', _('Pending Cancellation')), # User requested cancellation, active until end of cycle
    ('cancelled', _('Cancelled')), # Fully cancelled, no access
    ('past_due', _('Past Due')), # Payment failed, grace period might apply
    ('incomplete', _('Incomplete')), # Initial payment failed or requires action
    ('trialing', _('Trialing')),
]

class SubscriptionPlan(models.Model):
    """
    Defines different subscription plans available (e.g., Basic Monthly, Premium Annually).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, verbose_name=_('Plan Name'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))
    
    # Stripe Price ID (price_xxxx) associated with this plan in Stripe
    # This is crucial for creating subscriptions with Stripe.
    stripe_price_id = models.CharField(
        max_length=100,
        unique=True, # Each plan in your system should map to one Stripe Price ID
        verbose_name=_('Stripe Price ID'),
        help_text=_("The Price ID from Stripe (e.g., price_xxxxxxxxxxxxxx).")
    )
    # Stripe Product ID (prod_xxxx) can also be stored if you manage products separately in Stripe.
    # stripe_product_id = models.CharField(max_length=100, blank=True, null=True, verbose_name=_('Stripe Product ID'))


    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Price per Cycle'))
    currency = models.CharField(
        max_length=3,
        default='USD',
        choices=settings.CURRENCY_CHOICES, # Ensure CURRENCY_CHOICES is in settings.py
        verbose_name=_('Currency')
    )
    billing_cycle = models.CharField(
        max_length=20,
        choices=BILLING_CYCLE_CHOICES,
        default='monthly',
        verbose_name=_('Billing Cycle')
    )
    
    # Features or limits associated with this plan (e.g., number of courses, access level)
    # This could be a JSONField or related models depending on complexity.
    features = models.JSONField(default=dict, blank=True, null=True, verbose_name=_('Plan Features'), help_text=_("e.g., {'max_courses': 10, 'support_level': 'basic'}"))

    is_active = models.BooleanField(default=True, verbose_name=_('Is Active'), help_text=_("Is this plan currently available for new subscriptions?"))
    display_order = models.PositiveIntegerField(default=0, verbose_name=_('Display Order'), help_text=_("Order in which to display plans to users."))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Subscription Plan')
        verbose_name_plural = _('Subscription Plans')
        ordering = ['display_order', 'price']

    def __str__(self):
        return f"{self.name} ({self.price} {self.currency}/{self.billing_cycle})"


class UserSubscription(models.Model):
    """
    Tracks a user's subscription to a specific plan.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField( # Typically, a user has one active subscription at a time.
                                # If multiple subscriptions are allowed, change to ForeignKey.
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription',
        verbose_name=_('User')
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL, # Don't delete subscription if plan is deleted, just mark as inactive or handle
        null=True, # Plan might be deleted or changed
        related_name='user_subscriptions',
        verbose_name=_('Subscription Plan')
    )
    
    # Stripe Subscription ID (sub_xxxx)
    stripe_subscription_id = models.CharField(
        max_length=100,
        unique=True, # Each active subscription in your system maps to one Stripe Subscription
        verbose_name=_('Stripe Subscription ID'),
        help_text=_("The Subscription ID from Stripe (e.g., sub_xxxxxxxxxxxxxx).")
    )
    # Stripe Customer ID (cus_xxxx) - useful to store this per user or per subscription
    stripe_customer_id = models.CharField(
        max_length=100,
        verbose_name=_('Stripe Customer ID'),
        help_text=_("The Customer ID from Stripe (e.g., cus_xxxxxxxxxxxxxx). Often stored on UserProfile too.")
    )

    status = models.CharField(
        max_length=25,
        choices=SUBSCRIPTION_STATUS_CHOICES,
        default='inactive',
        verbose_name=_('Subscription Status')
    )
    
    current_period_start = models.DateTimeField(null=True, blank=True, verbose_name=_('Current Period Start'))
    current_period_end = models.DateTimeField(null=True, blank=True, verbose_name=_('Current Period End / Renewal Date'))
    cancel_at_period_end = models.BooleanField(default=False, verbose_name=_('Cancel at Period End'))
    
    # If you offer trials
    trial_start = models.DateTimeField(null=True, blank=True, verbose_name=_('Trial Start Date'))
    trial_end = models.DateTimeField(null=True, blank=True, verbose_name=_('Trial End Date'))

    # Metadata from Stripe or your system
    metadata = models.JSONField(default=dict, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Cancelled At')) # When it was actually cancelled

    class Meta:
        verbose_name = _('User Subscription')
        verbose_name_plural = _('User Subscriptions')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email}'s subscription to {self.plan.name if self.plan else 'N/A'}"

    @property
    def is_active(self):
        """Checks if the subscription is currently active and within the period."""
        return self.status == 'active' and (self.current_period_end is None or self.current_period_end >= timezone.now())

    @property
    def is_trialing(self):
        """Checks if the subscription is currently in a trial period."""
        return self.status == 'trialing' and (self.trial_end is None or self.trial_end >= timezone.now())


class PaymentTransaction(models.Model):
    """
    Records individual payment transactions, often linked to Stripe Invoices or Charges.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep transaction record even if user is deleted
        null=True,
        related_name='payment_transactions',
        verbose_name=_('User')
    )
    # Link to subscription if this payment is for a subscription renewal
    user_subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_transactions',
        verbose_name=_('Associated Subscription')
    )
    # If you have one-time purchases for specific items (e.g., a single course)
    # course_purchased = models.ForeignKey(
    #     'courses.Course', # Use string reference to avoid circular import if Course model is in another app
    #     on_delete=models.SET_NULL,
    #     null=True, blank=True,
    #     related_name='purchase_transactions'
    # )
    # item_description = models.CharField(max_length=255, blank=True, null=True, help_text="e.g., 'Subscription Renewal: Premium Plan' or 'Course: Intro to Python'")


    # Stripe Payment Intent ID (pi_xxxx) or Charge ID (ch_xxxx) or Invoice ID (in_xxxx)
    stripe_charge_id = models.CharField(
        max_length=100,
        unique=True, # Stripe IDs are unique
        verbose_name=_('Stripe Charge/PaymentIntent ID'),
        help_text=_("The ID of the charge or payment intent from Stripe.")
    )
    stripe_invoice_id = models.CharField(
        max_length=100,
        null=True, blank=True, # Not all payments are tied to invoices (e.g., direct charges)
        verbose_name=_('Stripe Invoice ID (if applicable)')
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Amount Paid'))
    currency = models.CharField(
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
        verbose_name=_('Currency')
    )
    status = models.CharField(
        max_length=25,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending',
        verbose_name=_('Payment Status')
    )
    payment_method_details = models.JSONField(default=dict, blank=True, null=True, verbose_name=_('Payment Method Details'), help_text=_("e.g., card brand, last4"))
    
    # Description for the payment
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Description'))
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Transaction Initiated At')) # When record created in our system
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Paid At')) # When Stripe confirmed payment
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Last Updated At'))

    # Full Stripe event object can be stored for auditing if needed
    stripe_event_data = models.JSONField(default=dict, blank=True, null=True, verbose_name=_('Stripe Event Data Snapshot'))


    class Meta:
        verbose_name = _('Payment Transaction')
        verbose_name_plural = _('Payment Transactions')
        ordering = ['-created_at']

    def __str__(self):
        user_email = self.user.email if self.user else "N/A"
        return f"Payment {self.id} by {user_email} - {self.amount} {self.currency} ({self.status})"

# --- Optional: Discount/Coupon Models ---
# class Coupon(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     code = models.CharField(max_length=50, unique=True, verbose_name=_('Coupon Code'))
#     # discount_type = models.CharField(max_length=10, choices=[('percentage', '%'), ('fixed', '$')])
#     # discount_value = models.DecimalField(max_digits=10, decimal_places=2)
#     # valid_from = models.DateTimeField()
#     # valid_to = models.DateTimeField()
#     # max_uses = models.PositiveIntegerField(null=True, blank=True)
#     # times_used = models.PositiveIntegerField(default=0)
#     # stripe_coupon_id = models.CharField(max_length=100, blank=True, null=True) # If managed in Stripe
#     # applicable_plans = models.ManyToManyField(SubscriptionPlan, blank=True)
#     pass

# class UserCouponUsage(models.Model):
#     user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
#     coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
#     used_at = models.DateTimeField(auto_now_add=True)
#     # payment_transaction = models.ForeignKey(PaymentTransaction, null=True, blank=True, on_delete=models.SET_NULL)
#     pass
