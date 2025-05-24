from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import SubscriptionPlan, UserSubscription, PaymentTransaction

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    """
    Admin configuration for the SubscriptionPlan model.
    """
    list_display = (
        'name', 'stripe_price_id', 'price', 'currency',
        'billing_cycle', 'is_active', 'display_order', 'created_at'
    )
    list_filter = ('is_active', 'billing_cycle', 'currency')
    search_fields = ('name', 'description', 'stripe_price_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('name', 'description', 'is_active', 'display_order')}),
        (_('Stripe & Pricing Details'), {'fields': (
            'stripe_price_id', 'price', 'currency', 'billing_cycle'
        )}),
        (_('Features'), {'fields': ('features',)}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    ordering = ('display_order', 'name')

    def get_readonly_fields(self, request, obj=None):
        # Make stripe_price_id readonly after creation, as changing it can break Stripe integration
        # unless carefully managed.
        if obj: # Editing an existing object
            return self.readonly_fields + ('stripe_price_id',)
        return self.readonly_fields


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    """
    Admin configuration for the UserSubscription model.
    Primarily for viewing and potentially manual status updates by admins in rare cases.
    Most status changes should come from Stripe webhooks.
    """
    list_display = (
        'user_email', 'plan_name', 'stripe_subscription_id', 'status',
        'current_period_end', 'cancel_at_period_end', 'is_active_property', 'created_at'
    )
    list_filter = ('status', 'plan__name', 'cancel_at_period_end', 'current_period_end')
    search_fields = (
        'user__email', 'user__username', 'plan__name',
        'stripe_subscription_id', 'stripe_customer_id'
    )
    readonly_fields = (
        'id', 'user', 'plan', # Plan should be changed via Stripe, not directly here usually
        'stripe_subscription_id', 'stripe_customer_id',
        'current_period_start', 'current_period_end',
        'trial_start', 'trial_end',
        'created_at', 'updated_at', 'cancelled_at',
        'metadata' # Usually from Stripe
    )
    fieldsets = (
        (_('Subscription Core Info'), {'fields': (
            'user', 'plan', 'stripe_subscription_id', 'stripe_customer_id'
        )}),
        (_('Status & Period'), {'fields': (
            'status', 'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'cancelled_at'
        )}),
        (_('Trial Information'), {'fields': ('trial_start', 'trial_end')}),
        (_('Metadata & Timestamps'), {'fields': ('metadata', 'created_at', 'updated_at')}),
    )
    list_select_related = ('user', 'plan') # Optimize queries
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = _('User Email')
    user_email.admin_order_field = 'user__email'

    def plan_name(self, obj):
        return obj.plan.name if obj.plan else _('N/A')
    plan_name.short_description = _('Plan')
    plan_name.admin_order_field = 'plan__name'

    def is_active_property(self, obj):
        return obj.is_active
    is_active_property.short_description = _('Currently Active?')
    is_active_property.boolean = True


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    """
    Admin configuration for the PaymentTransaction model.
    Primarily for viewing transaction history. Transactions are system-generated.
    """
    list_display = (
        'id', 'user_email', 'amount_with_currency', 'status',
        'stripe_charge_id', 'paid_at_formatted', 'created_at_formatted'
    )
    list_filter = ('status', 'currency', 'created_at', 'paid_at', 'user_subscription__plan__name')
    search_fields = (
        'user__email', 'user__username', 'stripe_charge_id',
        'stripe_invoice_id', 'description', 'user_subscription__stripe_subscription_id'
    )
    readonly_fields = ( # All fields are typically read-only as they come from Stripe
        'id', 'user', 'user_subscription', #'course_purchased',
        'stripe_charge_id', 'stripe_invoice_id',
        'amount', 'currency', 'status',
        'payment_method_details', 'description',
        'created_at', 'paid_at', 'updated_at', 'stripe_event_data'
    )
    fieldsets = (
        (_('Transaction Identity'), {'fields': (
            'id', 'user', 'user_subscription', #'course_purchased',
             'stripe_charge_id', 'stripe_invoice_id'
        )}),
        (_('Amount & Status'), {'fields': ('amount', 'currency', 'status', 'description')}),
        (_('Details & Timestamps'), {'fields': (
            'payment_method_details', 'paid_at', 'created_at', 'updated_at'
        )}),
        (_('Stripe Event Data'), {'fields': ('stripe_event_data',)}),
    )
    list_select_related = ('user', 'user_subscription', 'user_subscription__plan') # Optimize queries
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email if obj.user else _('N/A')
    user_email.short_description = _('User Email')
    user_email.admin_order_field = 'user__email'

    def amount_with_currency(self, obj):
        return f"{obj.amount} {obj.currency}"
    amount_with_currency.short_description = _('Amount')
    amount_with_currency.admin_order_field = 'amount' # Allows sorting by amount

    def paid_at_formatted(self, obj):
        return obj.paid_at.strftime("%Y-%m-%d %H:%M") if obj.paid_at else '-'
    paid_at_formatted.short_description = _('Paid At')
    paid_at_formatted.admin_order_field = 'paid_at'

    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%Y-%m-%d %H:%M")
    created_at_formatted.short_description = _('Recorded At')
    created_at_formatted.admin_order_field = 'created_at'

