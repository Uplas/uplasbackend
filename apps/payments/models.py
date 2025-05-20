from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone # Ensure timezone is imported for UserSubscription save logic
import uuid
from django.utils.text import slugify


class SubscriptionPlan(models.Model):
    PLAN_TIER_CHOICES = [
        ('free', _('Free')),
        ('basic', _('Basic')),
        ('premium', _('Premium')),
        ('enterprise', _('Enterprise')),
    ]
    BILLING_INTERVAL_CHOICES = [
        ('month', _('Monthly')),
        ('year', _('Annually')),
        ('one_time', _('One-Time')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Plan Name"), max_length=100, unique=True)
    tier_level = models.CharField(
        _("Plan Tier"),
        max_length=20,
        choices=PLAN_TIER_CHOICES,
        default='basic'
    )
    slug = models.SlugField(_("Slug"), max_length=120, unique=True, blank=True, help_text=_("URL-friendly identifier, auto-generated if blank."))
    description = models.TextField(_("Description"), blank=True, null=True)
    price = models.DecimalField(_("Price"), max_digits=10, decimal_places=2)
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        choices=settings.CURRENCY_CHOICES if hasattr(settings, 'CURRENCY_CHOICES') else [('USD', 'USD')],
        default='USD'
    )
    billing_interval = models.CharField(
        _("Billing Interval"),
        max_length=10,
        choices=BILLING_INTERVAL_CHOICES,
        default='month'
    )
    stripe_price_id = models.CharField(
        _("Stripe Price ID"),
        max_length=255,
        blank=True, null=True,
        unique=True, # A Stripe Price ID should uniquely identify one of our plans
        help_text=_("Stripe API Price ID (e.g., price_xxxxxxxxxxxxxx). Must be unique.")
    )
    features = models.JSONField(
        _("Features"),
        default=list, blank=True,
        help_text=_("List of features included in this plan.")
    )
    is_active = models.BooleanField(
        _("Active"), default=True,
        help_text=_("Whether this plan is currently available for new subscriptions.")
    )
    display_order = models.PositiveIntegerField(_("Display Order"), default=0, help_text=_("Order on pricing page."))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Subscription Plan")
        verbose_name_plural = _("Subscription Plans")
        ordering = ['display_order', 'price']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.billing_interval}")
            # Ensure slug uniqueness
            original_slug = self.slug
            counter = 1
            while SubscriptionPlan.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_billing_interval_display()} - {self.price} {self.currency})"

class UserSubscription(models.Model):
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('trialing', _('Trialing')),
        ('past_due', _('Past Due')), # Payment failed for renewal
        ('canceled', _('Canceled')), # User initiated cancellation, or admin after grace period
        ('unpaid', _('Unpaid')), # Stripe's state for subscriptions that are failing payment.
        ('incomplete', _('Incomplete')), # Checkout started but not completed
        ('incomplete_expired', _('Incomplete Expired')), # Checkout session expired
        ('ended', _('Ended')), # Subscription completed its lifecycle without renewal (e.g., fixed term non-renewing)
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, related_name='user_subscriptions')
    
    stripe_subscription_id = models.CharField(
        _("Stripe Subscription ID"),
        max_length=255,
        unique=True, null=True, blank=True # Unique, but can be null before Stripe sub is created
    )
    # We decided to store stripe_customer_id on the User model.
    # It can be useful to also have it here for quick reference with the subscription if needed.
    stripe_customer_id = models.CharField( 
        _("Stripe Customer ID (Reference)"), # From user.stripe_customer_id
        max_length=255,
        null=True, blank=True,
        help_text="Copied from User model for reference at the time of subscription event."
    )
    
    status = models.CharField(
        _("Status (from Stripe)"), # Indicate this is Stripe's status
        max_length=25,
        choices=STATUS_CHOICES,
        default='incomplete' # Default to incomplete before Stripe confirmation
    )
    
    start_date = models.DateTimeField(_("Start Date"), null=True, blank=True)
    current_period_start = models.DateTimeField(_("Current Period Start"), null=True, blank=True)
    current_period_end = models.DateTimeField(_("Current Period End"), null=True, blank=True)
    cancel_at_period_end = models.BooleanField(
        _("Cancel at Period End (Stripe)"),
        default=False,
        help_text=_("If true, Stripe will cancel the subscription at the end of the current period.")
    )
    canceled_at = models.DateTimeField(_("Canceled At (Stripe)"), null=True, blank=True) # When Stripe confirms cancellation
    ended_at = models.DateTimeField(_("Ended At (Stripe)"), null=True, blank=True) # If subscription truly ends (e.g., non-renewing fixed plan)

    trial_start_date = models.DateTimeField(_("Trial Start Date"), null=True, blank=True)
    trial_end_date = models.DateTimeField(_("Trial End Date"), null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True) # Our record creation
    updated_at = models.DateTimeField(auto_now=True) # Our record update

    class Meta:
        verbose_name = _("User Subscription")
        verbose_name_plural = _("User Subscriptions")
        ordering = ['-created_at']

    def __str__(self):
        plan_name = self.plan.name if self.plan else "N/A"
        return f"{self.user.email}'s Subscription to {plan_name} ({self.status})"

    def is_currently_active(self): # More precise active check
        """Checks if the subscription is effectively active for providing service."""
        return self.status in ['active', 'trialing'] and \
               (self.current_period_end is None or self.current_period_end >= timezone.now())

    def save(self, *args, **kwargs):
        # Ensure stripe_customer_id is synced from user if user is set
        if self.user and self.user.stripe_customer_id and not self.stripe_customer_id:
            self.stripe_customer_id = self.user.stripe_customer_id

        super().save(*args, **kwargs) # Save first to get an ID if creating

        # Update User model's denormalized premium status fields
        # This should ideally be robust and handle cases where user object might not be fully loaded
        try:
            user_to_update = User.objects.get(pk=self.user_id) # Fresh instance
            is_premium_now = self.is_currently_active()
            
            needs_user_save = False
            if user_to_update.is_premium_subscriber != is_premium_now:
                user_to_update.is_premium_subscriber = is_premium_now
                needs_user_save = True
            
            new_plan_name = self.plan.name if self.plan and is_premium_now else None
            if user_to_update.subscription_plan_name != new_plan_name:
                user_to_update.subscription_plan_name = new_plan_name
                needs_user_save = True

            new_sub_end_date = self.current_period_end.date() if self.current_period_end and is_premium_now else None
            if user_to_update.subscription_end_date != new_sub_end_date:
                user_to_update.subscription_end_date = new_sub_end_date
                needs_user_save = True

            if needs_user_save:
                user_to_update.save(update_fields=['is_premium_subscriber', 'subscription_plan_name', 'subscription_end_date'])
        except User.DoesNotExist:
            # Log this error, user associated with subscription doesn't exist
            pass


class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('subscription_signup', _('Subscription Signup')),
        ('subscription_renewal', _('Subscription Renewal')),
        ('one_time_purchase', _('One-Time Purchase')),
        ('refund', _('Refund')),
        ('credit_adjustment', _('Credit Adjustment')),
        ('payment_intent', _('Payment Intent')), # General payment intent
    ]
    TRANSACTION_STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('succeeded', _('Succeeded')),
        ('failed', _('Failed')),
        ('requires_action', _('Requires Action')),
        ('requires_payment_method', _('Requires Payment Method')),
        ('requires_confirmation', _('Requires Confirmation')),
        ('processing', _('Processing')),
        ('canceled', _('Canceled')), # For payment intents
        ('refunded', _('Refunded')), # For charges
        ('partially_refunded', _('Partially Refunded')), # For charges
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='transactions')
    user_subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transactions'
    )
    
    # Stripe IDs: A transaction could be related to an Invoice, a PaymentIntent, or a Charge.
    stripe_payment_intent_id = models.CharField(_("Stripe Payment Intent ID"), max_length=255, unique=True, null=True, blank=True)
    stripe_charge_id = models.CharField(_("Stripe Charge ID"), max_length=255, unique=True, null=True, blank=True) # Often part of PaymentIntent
    stripe_invoice_id = models.CharField(_("Stripe Invoice ID"), max_length=255, null=True, blank=True, db_index=True) # Invoices can have multiple payment attempts

    transaction_type = models.CharField(
        _("Transaction Type"),
        max_length=30,
        choices=TRANSACTION_TYPE_CHOICES,
        default='payment_intent'
    )
    status = models.CharField(
        _("Status (from Stripe)"),
        max_length=30, # Increased length for more Stripe statuses
        choices=TRANSACTION_STATUS_CHOICES,
        default='pending'
    )
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2) # Amount in major currency unit
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        choices=settings.CURRENCY_CHOICES if hasattr(settings, 'CURRENCY_CHOICES') else [('USD', 'USD')],
        default='USD'
    )
    
    payment_method_details = models.JSONField(_("Payment Method Details (from Stripe)"), null=True, blank=True)
    description = models.TextField(_("Description (from Stripe or internal)"), blank=True, null=True)
    
    error_message = models.TextField(_("Error Message (if failed, from Stripe)"), blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True) # Our record creation time
    processed_at = models.DateTimeField(_("Processed At (Stripe event time)"), null=True, blank=True) # When Stripe event occurred

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")
        ordering = ['-processed_at', '-created_at'] # Order by when Stripe processed it primarily

    def __str__(self):
        user_email = self.user.email if self.user else 'N/A'
        return f"Transaction {self.id} for {user_email} - {self.amount} {self.currency} ({self.status})"
