from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import uuid

# Re-using User model from the users app
# from apps.users.models import User # Not needed directly, settings.AUTH_USER_MODEL is used
# Re-using Course model for potential one-time course purchases if needed in future
# from apps.courses.models import Course

class SubscriptionPlan(models.Model):
    """
    Defines the available subscription plans (e.g., Free, Basic, Premium).
    
    """
    PLAN_TIER_CHOICES = [
        ('free', _('Free')),
        ('basic', _('Basic')),
        ('premium', _('Premium')),
        ('enterprise', _('Enterprise')), # For custom/larger plans
    ]
    BILLING_INTERVAL_CHOICES = [
        ('month', _('Monthly')),
        ('year', _('Annually')),
        ('one_time', _('One-Time')), # For non-recurring plans or specific access
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Plan Name"), max_length=100, unique=True) # e.g., "Uplas Premium Monthly"
    tier_level = models.CharField( # Used for easy reference to plan type
        _("Plan Tier"),
        max_length=20,
        choices=PLAN_TIER_CHOICES,
        default='basic'
    )
    slug = models.SlugField(_("Slug"), max_length=120, unique=True, blank=True, help_text=_("URL-friendly identifier"))
    description = models.TextField(_("Description"), blank=True, null=True)
    price = models.DecimalField(_("Price"), max_digits=10, decimal_places=2)
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        choices=settings.CURRENCY_CHOICES, # From project settings
        default='USD'
    )
    billing_interval = models.CharField(
        _("Billing Interval"),
        max_length=10,
        choices=BILLING_INTERVAL_CHOICES,
        default='month'
    )
    # Stripe specific IDs for this plan/price
    stripe_price_id = models.CharField(
        _("Stripe Price ID"),
        max_length=255,
        blank=True, null=True,
        help_text=_("Stripe API Price ID (e.g., price_xxxxxxxxxxxxxx)")
    )
    # stripe_product_id = models.CharField( # Product ID can be associated with multiple prices
    #     _("Stripe Product ID"),
    #     max_length=255,
    #     blank=True, null=True,
    #     help_text=_("Stripe API Product ID (e.g., prod_xxxxxxxxxxxxxx)")
    # )

    features = models.JSONField(
        _("Features"),
        default=list, blank=True,
        help_text=_("List of features included in this plan, e.g., ['Unlimited AI Tutor', 'Access to All Courses']")
    )
    is_active = models.BooleanField(
        _("Active"), default=True,
        help_text=_("Whether this plan is currently available for new subscriptions")
    )
    display_order = models.PositiveIntegerField(_("Display Order"), default=0, help_text=_("Order on pricing page"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Subscription Plan")
        verbose_name_plural = _("Subscription Plans")
        ordering = ['display_order', 'price']

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.billing_interval}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_billing_interval_display()} - {self.price} {self.currency})"


class UserSubscription(models.Model):
    """
    Links a user to a subscription plan and tracks its status.
    
    """
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('pending_payment', _('Pending Payment')), # If initial payment fails or needs confirmation
        ('trialing', _('Trialing')),
        ('past_due', _('Past Due')), # Payment failed for renewal
        ('canceled', _('Canceled')), # User initiated cancellation, or admin
        ('expired', _('Expired')), # End of a non-renewing plan or trial
        ('incomplete', _('Incomplete')), # Stripe Checkout session started but not completed
        ('incomplete_expired', _('Incomplete Expired')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField( # Typically a user has one active primary subscription
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription' # Easy access: user.subscription
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, related_name='user_subscriptions')
    
    stripe_subscription_id = models.CharField(
        _("Stripe Subscription ID"),
        max_length=255,
        unique=True, null=True, blank=True # Nullable if not a Stripe subscription or before creation
    )
    stripe_customer_id = models.CharField( # Store Stripe Customer ID on User model or here
        _("Stripe Customer ID"),
        max_length=255,
        null=True, blank=True
    )
    
    status = models.CharField(
        _("Status"),
        max_length=25,
        choices=STATUS_CHOICES,
        default='pending_payment'
    )
    
    start_date = models.DateTimeField(_("Start Date"), null=True, blank=True) # When the subscription became active
    current_period_start = models.DateTimeField(_("Current Period Start"), null=True, blank=True)
    current_period_end = models.DateTimeField(_("Current Period End"), null=True, blank=True)
    cancel_at_period_end = models.BooleanField(
        _("Cancel at Period End"),
        default=False,
        help_text=_("If true, the subscription will cancel at the end of the current period.")
    )
    canceled_at = models.DateTimeField(_("Canceled At"), null=True, blank=True) # When the cancellation was processed

    trial_start_date = models.DateTimeField(_("Trial Start Date"), null=True, blank=True)
    trial_end_date = models.DateTimeField(_("Trial End Date"), null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("User Subscription")
        verbose_name_plural = _("User Subscriptions")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}'s Subscription to {self.plan.name if self.plan else 'N/A'}"

    def is_active_or_trialing(self):
        return self.status in ['active', 'trialing']
    
    def save(self, *args, **kwargs):
        # Update User model's is_premium_subscriber field based on this subscription's status
        if self.user:
            is_premium = self.is_active_or_trialing()
            if self.user.is_premium_subscriber != is_premium:
                self.user.is_premium_subscriber = is_premium
                self.user.subscription_plan = self.plan if is_premium else None
                self.user.subscription_end_date = self.current_period_end if is_premium else None
                self.user.save(update_fields=['is_premium_subscriber', 'subscription_plan', 'subscription_end_date'])
        super().save(*args, **kwargs)


class Transaction(models.Model):
    """
    Records individual payment transactions.
    
    """
    TRANSACTION_TYPE_CHOICES = [
        ('subscription_signup', _('Subscription Signup')),
        ('subscription_renewal', _('Subscription Renewal')),
        ('one_time_purchase', _('One-Time Purchase')), # e.g., for a single course if implemented
        ('refund', _('Refund')),
        ('credit_adjustment', _('Credit Adjustment')),
    ]
    TRANSACTION_STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('succeeded', _('Succeeded')),
        ('failed', _('Failed')),
        ('requires_action', _('Requires Action')), # e.g. 3D Secure
        ('refunded', _('Refunded')),
        ('partially_refunded', _('Partially Refunded')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='transactions')
    user_subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transactions',
        help_text=_("Associated subscription, if any")
    )
    # course = models.ForeignKey( # If you implement one-time course purchases
    #     'courses.Course',
    #     on_delete=models.SET_NULL,
    #     null=True, blank=True,
    #     related_name='transactions'
    # )
    
    stripe_charge_id = models.CharField(_("Stripe Charge ID / Payment Intent ID"), max_length=255, unique=True, null=True, blank=True)
    stripe_invoice_id = models.CharField(_("Stripe Invoice ID"), max_length=255, null=True, blank=True)


    transaction_type = models.CharField(
        _("Transaction Type"),
        max_length=30,
        choices=TRANSACTION_TYPE_CHOICES,
        default='subscription_signup'
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=TRANSACTION_STATUS_CHOICES,
        default='pending'
    )
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2)
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
        default='USD'
    )
    
    payment_method_details = models.JSONField(_("Payment Method Details"), null=True, blank=True, help_text=_("e.g., card brand, last4"))
    description = models.TextField(_("Description"), blank=True, null=True) # e.g. "Monthly subscription to Uplas Premium"
    
    error_message = models.TextField(_("Error Message (if failed)"), blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True) # When record created in our DB
    processed_at = models.DateTimeField(_("Processed At"), null=True, blank=True) # When payment gateway confirmed processing

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")
        ordering = ['-created_at']

    def __str__(self):
        return f"Transaction {self.id} for {self.user.username if self.user else 'N/A'} - {self.amount} {self.currency} ({self.status})"

# It's good practice to store Stripe Customer ID on the User model as well for quick access
# If you haven't already, add a field like:
# In apps/users/models.py User model:
# stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stripe Customer ID")
# And ensure it's populated when a customer is created in Stripe.
