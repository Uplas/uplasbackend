# uplasbackend/apps/payments/admin.py
from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription, PaymentTransaction

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'currency', 'billing_cycle', 'is_active', 'display_order')
    list_filter = ('is_active', 'billing_cycle', 'currency')
    search_fields = ('name', 'stripe_price_id')
    ordering = ('display_order', 'price')
    list_editable = ('is_active', 'display_order')

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'current_period_end', 'cancel_at_period_end')
    list_filter = ('status', 'plan', 'cancel_at_period_end')
    search_fields = ('user__email', 'plan__name', 'stripe_subscription_id', 'stripe_customer_id')
    autocomplete_fields = ('user', 'plan')
    readonly_fields = ('stripe_subscription_id', 'stripe_customer_id', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'currency', 'status', 'paid_at', 'user_subscription')
    list_filter = ('status', 'currency')
    search_fields = ('user__email', 'stripe_charge_id', 'user_subscription__stripe_subscription_id')
    autocomplete_fields = ('user', 'user_subscription')
    readonly_fields = ('stripe_charge_id', 'created_at', 'updated_at')
    date_hierarchy = 'paid_at'