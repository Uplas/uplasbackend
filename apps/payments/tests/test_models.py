from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import IntegrityError
from decimal import Decimal
from uuid import UUID

from apps.payments.models import (
    SubscriptionPlan, UserSubscription, PaymentTransaction,
    BILLING_CYCLE_CHOICES, PAYMENT_STATUS_CHOICES, SUBSCRIPTION_STATUS_CHOICES
)
# Ensure settings are configured for tests, especially AUTH_USER_MODEL and CURRENCY_CHOICES
from django.conf import settings

User = get_user_model()

class PaymentsModelTestDataMixin:
    """
    Mixin to provide common setup data for payment-related model tests.
    """
    @classmethod
    def setUpTestData(cls):
        # Create users
        cls.user1 = User.objects.create_user(
            username='payment_user1',
            email='paymentuser1@example.com',
            password='password123',
            full_name='Payment User One'
        )
        cls.user2 = User.objects.create_user(
            username='payment_user2',
            email='paymentuser2@example.com',
            password='password123',
            full_name='Payment User Two'
        )

        # Create Subscription Plans
        cls.plan_monthly = SubscriptionPlan.objects.create(
            name='Basic Monthly',
            stripe_price_id='price_monthly_basic_test',
            price=Decimal('9.99'),
            currency='USD',
            billing_cycle='monthly',
            features={'max_courses': 5, 'support': 'email'},
            is_active=True,
            display_order=1
        )
        cls.plan_annually = SubscriptionPlan.objects.create(
            name='Premium Annually',
            stripe_price_id='price_annually_premium_test',
            price=Decimal('99.99'),
            currency='USD',
            billing_cycle='annually',
            features={'max_courses': 'unlimited', 'support': 'priority'},
            is_active=True,
            display_order=0 # Higher priority display
        )
        cls.plan_inactive = SubscriptionPlan.objects.create(
            name='Old Quarterly Plan',
            stripe_price_id='price_quarterly_old_test',
            price=Decimal('25.00'),
            currency='USD',
            billing_cycle='quarterly',
            is_active=False # Inactive plan
        )

class SubscriptionPlanModelTests(PaymentsModelTestDataMixin, TestCase):
    def test_subscription_plan_creation(self):
        self.assertEqual(self.plan_monthly.name, 'Basic Monthly')
        self.assertEqual(self.plan_monthly.stripe_price_id, 'price_monthly_basic_test')
        self.assertEqual(self.plan_monthly.price, Decimal('9.99'))
        self.assertEqual(self.plan_monthly.currency, 'USD')
        self.assertEqual(self.plan_monthly.billing_cycle, 'monthly')
        self.assertTrue(self.plan_monthly.is_active)
        self.assertEqual(self.plan_monthly.features['max_courses'], 5)
        self.assertIsNotNone(self.plan_monthly.created_at)
        self.assertIsNotNone(self.plan_monthly.updated_at)
        self.assertEqual(str(self.plan_monthly), "Basic Monthly (9.99 USD/monthly)")

    def test_subscription_plan_stripe_price_id_uniqueness(self):
        with self.assertRaises(IntegrityError):
            SubscriptionPlan.objects.create(
                name='Duplicate Stripe ID Plan',
                stripe_price_id='price_monthly_basic_test', # Duplicate
                price=Decimal('10.00'),
                currency='USD',
                billing_cycle='monthly'
            )

    def test_subscription_plan_name_uniqueness(self):
        with self.assertRaises(IntegrityError):
            SubscriptionPlan.objects.create(
                name='Basic Monthly', # Duplicate
                stripe_price_id='price_another_test',
                price=Decimal('10.00'),
                currency='USD',
                billing_cycle='monthly'
            )

    def test_subscription_plan_ordering(self):
        plans = SubscriptionPlan.objects.filter(is_active=True) # Get active plans
        # display_order=0 (Premium Annually) should come before display_order=1 (Basic Monthly)
        self.assertEqual(plans[0], self.plan_annually)
        self.assertEqual(plans[1], self.plan_monthly)


class UserSubscriptionModelTests(PaymentsModelTestDataMixin, TestCase):
    def setUp(self):
        # This setup runs for each test method in this class
        self.subscription1 = UserSubscription.objects.create(
            user=self.user1,
            plan=self.plan_monthly,
            stripe_subscription_id='sub_test_user1_monthly',
            stripe_customer_id='cus_test_user1',
            status='active',
            current_period_start=timezone.now() - timezone.timedelta(days=10),
            current_period_end=timezone.now() + timezone.timedelta(days=20) # Active period
        )

    def test_user_subscription_creation(self):
        self.assertEqual(self.subscription1.user, self.user1)
        self.assertEqual(self.subscription1.plan, self.plan_monthly)
        self.assertEqual(self.subscription1.stripe_subscription_id, 'sub_test_user1_monthly')
        self.assertEqual(self.subscription1.status, 'active')
        self.assertTrue(self.subscription1.is_active) # Check property
        self.assertFalse(self.subscription1.is_trialing)
        self.assertEqual(str(self.subscription1), f"{self.user1.email}'s subscription to {self.plan_monthly.name}")

    def test_user_subscription_user_onetoone_constraint(self):
        # Try to create another subscription for user1 (should fail due to OneToOneField)
        with self.assertRaises(IntegrityError):
            UserSubscription.objects.create(
                user=self.user1, # Same user
                plan=self.plan_annually,
                stripe_subscription_id='sub_test_user1_annual_fail',
                stripe_customer_id='cus_test_user1_alt', # Can be same or different customer
                status='active'
            )

    def test_user_subscription_stripe_id_uniqueness(self):
        with self.assertRaises(IntegrityError):
            UserSubscription.objects.create(
                user=self.user2, # Different user
                plan=self.plan_annually,
                stripe_subscription_id='sub_test_user1_monthly', # Duplicate Stripe Sub ID
                stripe_customer_id='cus_test_user2',
                status='active'
            )

    def test_is_active_property(self):
        # Active subscription (created in setUp)
        self.assertTrue(self.subscription1.is_active)

        # Expired subscription
        expired_sub = UserSubscription.objects.create(
            user=self.user2, plan=self.plan_monthly, stripe_subscription_id='sub_expired',
            stripe_customer_id='cus_expired', status='active', # Status might still be 'active' from Stripe
            current_period_start=timezone.now() - timezone.timedelta(days=40),
            current_period_end=timezone.now() - timezone.timedelta(days=10) # Period ended
        )
        self.assertFalse(expired_sub.is_active)

        # Cancelled subscription
        self.subscription1.status = 'cancelled'
        self.subscription1.save()
        self.assertFalse(self.subscription1.is_active)

    def test_is_trialing_property(self):
        trial_sub = UserSubscription.objects.create(
            user=self.user2, plan=self.plan_monthly, stripe_subscription_id='sub_trial',
            stripe_customer_id='cus_trial', status='trialing',
            trial_start=timezone.now() - timezone.timedelta(days=5),
            trial_end=timezone.now() + timezone.timedelta(days=5) # Trial active
        )
        self.assertTrue(trial_sub.is_trialing)

        trial_sub.trial_end = timezone.now() - timezone.timedelta(days=1) # Trial ended
        trial_sub.save()
        self.assertFalse(trial_sub.is_trialing)

        trial_sub.status = 'active' # No longer trialing
        trial_sub.trial_end = timezone.now() + timezone.timedelta(days=5)
        trial_sub.save()
        self.assertFalse(trial_sub.is_trialing)


class PaymentTransactionModelTests(PaymentsModelTestDataMixin, TestCase):
    def setUp(self):
        self.user_subscription = UserSubscription.objects.create(
            user=self.user1, plan=self.plan_monthly,
            stripe_subscription_id='sub_for_txn_test', stripe_customer_id='cus_for_txn_test',
            status='active'
        )
        self.transaction1 = PaymentTransaction.objects.create(
            user=self.user1,
            user_subscription=self.user_subscription,
            stripe_charge_id='ch_test_transaction1',
            amount=self.plan_monthly.price,
            currency=self.plan_monthly.currency,
            status='succeeded',
            paid_at=timezone.now(),
            description="Monthly subscription payment"
        )

    def test_payment_transaction_creation(self):
        self.assertEqual(self.transaction1.user, self.user1)
        self.assertEqual(self.transaction1.user_subscription, self.user_subscription)
        self.assertEqual(self.transaction1.stripe_charge_id, 'ch_test_transaction1')
        self.assertEqual(self.transaction1.amount, self.plan_monthly.price)
        self.assertEqual(self.transaction1.status, 'succeeded')
        self.assertIsNotNone(self.transaction1.paid_at)
        self.assertEqual(str(self.transaction1), f"Payment {self.transaction1.id} by {self.user1.email} - {self.plan_monthly.price} {self.plan_monthly.currency} (succeeded)")

    def test_payment_transaction_stripe_charge_id_uniqueness(self):
        with self.assertRaises(IntegrityError):
            PaymentTransaction.objects.create(
                user=self.user2,
                stripe_charge_id='ch_test_transaction1', # Duplicate
                amount=Decimal('10.00'),
                currency='USD',
                status='succeeded'
            )

    def test_payment_transaction_defaults(self):
        # Test default status if not provided (should be 'pending' as per model)
        txn_with_default = PaymentTransaction.objects.create(
            user=self.user1,
            stripe_charge_id='ch_test_default_status',
            amount=Decimal('5.00'),
            currency='USD'
        )
        self.assertEqual(txn_with_default.status, 'pending')

# Add more tests for:
# - Edge cases for date comparisons in UserSubscription properties.
# - Behavior when related objects (User, SubscriptionPlan) are deleted (on_delete actions).
# - Any custom methods or complex logic added to the models.
# - Validation of JSONField content if a schema is enforced.
