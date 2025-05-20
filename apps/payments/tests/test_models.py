from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.db.utils import IntegrityError
from decimal import Decimal
from unittest.mock import patch # For mocking User model save if needed during UserSubscription save

from ..models import SubscriptionPlan, UserSubscription, Transaction
from apps.users.models import UserProfile # To ensure UserProfile exists for user.profile access

User = get_user_model()

class SubscriptionPlanModelTests(TestCase):

    def test_create_subscription_plan(self):
        """Test creating a SubscriptionPlan successfully."""
        plan_data = {
            "name": "Uplas Premium Monthly",
            "tier_level": "premium",
            "description": "Full access to all features.",
            "price": Decimal("19.99"),
            "currency": "USD",
            "billing_interval": "month",
            "stripe_price_id": "price_monthly_premium_123",
            "features": ["All courses", "AI Tutor Pro"],
            "is_active": True,
            "display_order": 1,
        }
        plan = SubscriptionPlan.objects.create(**plan_data)
        self.assertEqual(plan.name, plan_data["name"])
        self.assertEqual(plan.slug, slugify(f"{plan_data['name']}-{plan_data['billing_interval']}"))
        self.assertEqual(plan.price, plan_data["price"])
        self.assertEqual(plan.stripe_price_id, plan_data["stripe_price_id"])
        self.assertEqual(plan.features, plan_data["features"])
        self.assertTrue(plan.is_active)
        self.assertEqual(str(plan), "Uplas Premium Monthly (Monthly - 19.99 USD)")

    def test_subscription_plan_slug_uniqueness_on_create(self):
        """Test unique slug generation for similar plan names/intervals."""
        SubscriptionPlan.objects.create(name="Basic Plan", billing_interval="month", price=Decimal("9.99"))
        plan2 = SubscriptionPlan.objects.create(name="Basic Plan", billing_interval="month", price=Decimal("10.99")) # Should generate new slug
        
        expected_slug1 = slugify("Basic Plan-month")
        self.assertNotEqual(plan2.slug, expected_slug1)
        self.assertTrue(plan2.slug.startswith(expected_slug1 + "-"))

    def test_subscription_plan_stripe_price_id_uniqueness(self):
        """Test stripe_price_id must be unique."""
        stripe_id = "price_test_unique_789"
        SubscriptionPlan.objects.create(name="Plan A", stripe_price_id=stripe_id, price=Decimal("1.00"))
        with self.assertRaises(IntegrityError):
            SubscriptionPlan.objects.create(name="Plan B", stripe_price_id=stripe_id, price=Decimal("2.00"))


class UserSubscriptionModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="subuser@example.com", password="password", stripe_customer_id="cus_test123")
        # Ensure UserProfile exists for UserSubscription's save method that updates user.profile.stripe_customer_id (if it were there)
        # User model now has stripe_customer_id directly
        # UserProfile.objects.get_or_create(user=self.user) # Done by signal from User model

        self.plan_active = SubscriptionPlan.objects.create(
            name="Active Monthly", price=Decimal("10.00"), billing_interval="month", stripe_price_id="price_active_mo"
        )
        self.plan_trial = SubscriptionPlan.objects.create(
            name="Trial Plan", price=Decimal("0.00"), billing_interval="month", stripe_price_id="price_trial_mo"
        )

    def test_create_user_subscription(self):
        """Test creating a UserSubscription instance."""
        sub = UserSubscription.objects.create(
            user=self.user,
            plan=self.plan_active,
            stripe_subscription_id="sub_test_123",
            status='active',
            current_period_start=timezone.now() - timezone.timedelta(days=10),
            current_period_end=timezone.now() + timezone.timedelta(days=20)
        )
        self.assertEqual(sub.user, self.user)
        self.assertEqual(sub.plan, self.plan_active)
        self.assertEqual(sub.stripe_subscription_id, "sub_test_123")
        self.assertEqual(sub.status, 'active')
        self.assertEqual(sub.stripe_customer_id, self.user.stripe_customer_id) # Check if synced from user
        self.assertEqual(str(sub), f"{self.user.email}'s Subscription to {self.plan_active.name} (active)")

    def test_user_subscription_user_is_one_to_one(self):
        """Test that a user can only have one UserSubscription due to OneToOneField."""
        UserSubscription.objects.create(user=self.user, plan=self.plan_active, status='active')
        with self.assertRaises(IntegrityError):
            UserSubscription.objects.create(user=self.user, plan=self.plan_trial, status='trialing')

    def test_is_currently_active_method(self):
        """Test the is_currently_active method logic."""
        # Active and within period
        sub_active = UserSubscription(
            user=self.user, plan=self.plan_active, status='active',
            current_period_end=timezone.now() + timezone.timedelta(days=5)
        )
        self.assertTrue(sub_active.is_currently_active())

        # Trialing and within period
        sub_trial = UserSubscription(
            user=self.user, plan=self.plan_trial, status='trialing',
            current_period_end=timezone.now() + timezone.timedelta(days=2) # trial_end_date could also be used
        )
        self.assertTrue(sub_trial.is_currently_active())

        # Active but period ended
        sub_active_ended_period = UserSubscription(
            user=self.user, plan=self.plan_active, status='active',
            current_period_end=timezone.now() - timezone.timedelta(days=1)
        )
        self.assertFalse(sub_active_ended_period.is_currently_active())

        # Canceled status
        sub_canceled = UserSubscription(
            user=self.user, plan=self.plan_active, status='canceled',
            current_period_end=timezone.now() + timezone.timedelta(days=5)
        )
        self.assertFalse(sub_canceled.is_currently_active())

        # Past due status
        sub_past_due = UserSubscription(
            user=self.user, plan=self.plan_active, status='past_due',
            current_period_end=timezone.now() + timezone.timedelta(days=5) # Still technically in period but service might be cut
        )
        self.assertFalse(sub_past_due.is_currently_active()) # Our definition excludes past_due

    def test_user_subscription_save_updates_user_model_active_sub(self):
        """Test UserSubscription.save() updates User model for an active subscription."""
        self.assertFalse(self.user.is_premium_subscriber) # Initial state

        sub = UserSubscription.objects.create(
            user=self.user,
            plan=self.plan_active,
            status='active',
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30)
        )
        # sub.save() is called on create, then again by our logic for user update
        
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_premium_subscriber)
        self.assertEqual(self.user.subscription_plan_name, self.plan_active.name)
        self.assertEqual(self.user.subscription_end_date, sub.current_period_end.date())
        self.assertEqual(sub.stripe_customer_id, self.user.stripe_customer_id)


    def test_user_subscription_save_updates_user_model_trial_sub(self):
        """Test UserSubscription.save() updates User model for a trialing subscription."""
        self.assertFalse(self.user.is_premium_subscriber)
        trial_end = timezone.now() + timezone.timedelta(days=7)
        sub = UserSubscription.objects.create(
            user=self.user,
            plan=self.plan_trial,
            status='trialing',
            trial_end_date=trial_end, # Assuming trial_end_date implies current_period_end for trial
            current_period_end=trial_end
        )
        
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_premium_subscriber)
        self.assertEqual(self.user.subscription_plan_name, self.plan_trial.name)
        self.assertEqual(self.user.subscription_end_date, trial_end.date())

    def test_user_subscription_save_updates_user_model_canceled_sub(self):
        """Test UserSubscription.save() updates User model for a canceled subscription."""
        # First, make it active
        active_end = timezone.now() + timezone.timedelta(days=15)
        sub = UserSubscription.objects.create(
            user=self.user, plan=self.plan_active, status='active', current_period_end=active_end
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_premium_subscriber)

        # Now, cancel it
        sub.status = 'canceled'
        sub.canceled_at = timezone.now()
        sub.current_period_end = timezone.now() # Typically cancellation ends the current period effectively
        sub.save() # Trigger the update logic

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_premium_subscriber)
        self.assertIsNone(self.user.subscription_plan_name)
        self.assertIsNone(self.user.subscription_end_date)

    def test_user_subscription_syncs_stripe_customer_id_from_user_if_missing(self):
        """Test UserSubscription syncs stripe_customer_id from User if it's missing on self."""
        self.user.stripe_customer_id = "cus_updated_on_user"
        self.user.save()

        sub = UserSubscription.objects.create(
            user=self.user,
            plan=self.plan_active,
            status='active',
            stripe_customer_id=None # Explicitly set to None on sub
        )
        sub.refresh_from_db() # After create and its save() call
        self.assertEqual(sub.stripe_customer_id, "cus_updated_on_user")


class TransactionModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="transactionuser@example.com", password="password")
        self.plan = SubscriptionPlan.objects.create(name="Trans Plan", price=Decimal("5.00"))
        self.subscription = UserSubscription.objects.create(user=self.user, plan=self.plan, status='active')

    def test_create_transaction(self):
        """Test creating a Transaction successfully."""
        now = timezone.now()
        transaction_data = {
            "user": self.user,
            "user_subscription": self.subscription,
            "stripe_payment_intent_id": "pi_test_123abc",
            "stripe_invoice_id": "in_test_123",
            "transaction_type": "subscription_renewal",
            "status": "succeeded",
            "amount": Decimal("5.00"),
            "currency": "USD",
            "payment_method_details": {"card_brand": "visa", "card_last4": "4242"},
            "description": "Monthly renewal for Trans Plan",
            "processed_at": now
        }
        transaction = Transaction.objects.create(**transaction_data)
        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.stripe_payment_intent_id, transaction_data["stripe_payment_intent_id"])
        self.assertEqual(transaction.amount, transaction_data["amount"])
        self.assertEqual(transaction.status, "succeeded")
        self.assertEqual(str(transaction), f"Transaction {transaction.id} for {self.user.email} - 5.00 USD (succeeded)")

    def test_transaction_uniqueness_for_stripe_ids(self):
        """Test unique constraints on Stripe IDs."""
        common_pi_id = "pi_unique_test_001"
        common_charge_id = "ch_unique_test_001"

        Transaction.objects.create(user=self.user, stripe_payment_intent_id=common_pi_id, amount=1, currency="USD")
        with self.assertRaises(IntegrityError):
            Transaction.objects.create(user=self.user, stripe_payment_intent_id=common_pi_id, amount=2, currency="USD")

        Transaction.objects.create(user=self.user, stripe_charge_id=common_charge_id, amount=3, currency="USD")
        with self.assertRaises(IntegrityError):
            Transaction.objects.create(user=self.user, stripe_charge_id=common_charge_id, amount=4, currency="USD")

        # Test nulls are fine for uniqueness
        Transaction.objects.create(user=self.user, stripe_payment_intent_id=None, stripe_charge_id=None, amount=5, currency="USD")
        Transaction.objects.create(user=self.user, stripe_payment_intent_id=None, stripe_charge_id=None, amount=6, currency="USD")
        self.assertTrue(True) # If it reaches here
