from django.test import TestCase
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.test import APIRequestFactory # To create mock request for context
from decimal import Decimal
import uuid

from ..models import SubscriptionPlan, UserSubscription, Transaction
from ..serializers import (
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
    TransactionSerializer,
    CreateSubscriptionCheckoutSessionSerializer
)
# Assuming BasicUserSerializerForPayments is defined in payments.serializers for tests if not importing
# from apps.users.serializers import BasicUserSerializer # Or your actual basic user serializer

User = get_user_model()

# If BasicUserSerializerForPayments is not defined in payments.serializers,
# include a minimal version for these tests to run:
if not hasattr(UserSubscriptionSerializer.Meta, 'fields') or 'user' not in UserSubscriptionSerializer.Meta.fields or not hasattr(UserSubscriptionSerializer.user, 'serializer_class'):
    class BasicUserSerializerForPayments(serializers.ModelSerializer):
        class Meta:
            model = User
            fields = ['id', 'username', 'email', 'full_name']
            read_only_fields = fields

    # Monkey patch if needed for tests if the actual serializer isn't robustly defined/imported
    if hasattr(UserSubscriptionSerializer, 'user'):
         UserSubscriptionSerializer.user.serializer_class = BasicUserSerializerForPayments
    if hasattr(TransactionSerializer, 'user'):
        TransactionSerializer.user.serializer_class = BasicUserSerializerForPayments


class SubscriptionPlanSerializerTests(TestCase):

    def test_subscription_plan_serializer_output_data(self):
        """Test SubscriptionPlanSerializer serializes data correctly."""
        plan_data = {
            "name": "Pro Monthly",
            "tier_level": "premium",
            "price": Decimal("29.99"),
            "currency": "USD",
            "billing_interval": "month",
            "stripe_price_id": "price_pro_monthly_xyz",
            "features": ["Feature A", "Feature B"],
            "is_active": True
        }
        plan = SubscriptionPlan.objects.create(**plan_data)
        serializer = SubscriptionPlanSerializer(plan)
        data = serializer.data

        self.assertEqual(data['name'], plan_data['name'])
        self.assertEqual(data['tier_level'], plan_data['tier_level'])
        self.assertEqual(Decimal(data['price']), plan_data['price']) # Compare as Decimal
        self.assertEqual(data['stripe_price_id'], plan_data['stripe_price_id'])
        self.assertEqual(data['features'], plan_data['features'])
        self.assertTrue(data['is_active'])
        self.assertIn('slug', data) # Slug is auto-generated

    def test_subscription_plan_serializer_read_only_fields(self):
        """Test read-only fields are not accepted on creation/update directly."""
        # This is more about how DRF handles read_only_fields during deserialization.
        # If data for a read_only_field is passed, it should be ignored.
        plan_data_with_readonly = {
            "name": "Test ReadOnly",
            "price": Decimal("5.00"),
            "slug": "should-be-ignored", # read_only
            "is_active": False # Not read_only but good to test setting
        }
        serializer = SubscriptionPlanSerializer(data=plan_data_with_readonly)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        plan = serializer.save() # Slug should be auto-generated, not 'should-be-ignored'
        self.assertNotEqual(plan.slug, "should-be-ignored")
        self.assertTrue(plan.slug.startswith(slugify("Test ReadOnly")))
        self.assertFalse(plan.is_active) # Check writable field was set


class UserSubscriptionSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="usersubserializer@example.com",
            password="password",
            full_name="Sub Serializer User",
            stripe_customer_id="cus_usersubtest"
        )
        self.plan = SubscriptionPlan.objects.create(
            name="Gold Plan", price=Decimal("50.00"), stripe_price_id="price_gold_123"
        )
        self.subscription = UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            stripe_subscription_id="sub_goldplanuser",
            stripe_customer_id=self.user.stripe_customer_id, # Synced from user
            status='active',
            current_period_end=timezone.now() + timezone.timedelta(days=15)
        )
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
        self.request.user = self.user

    def test_user_subscription_serializer_output_data(self):
        """Test UserSubscriptionSerializer serializes data correctly."""
        serializer = UserSubscriptionSerializer(self.subscription, context={'request': self.request})
        data = serializer.data

        self.assertEqual(data['id'], str(self.subscription.id))
        self.assertEqual(data['user']['email'], self.user.email)
        self.assertEqual(data['plan']['name'], self.plan.name)
        self.assertEqual(data['stripe_subscription_id'], self.subscription.stripe_subscription_id)
        self.assertEqual(data['status'], 'active')
        self.assertTrue(data['is_currently_active']) # Check model property serialization
        self.assertIsNotNone(data['current_period_end'])

    def test_user_subscription_serializer_read_only(self):
        """Ensure most fields are read-only as they are Stripe-managed."""
        # Attempting to update a read-only field via serializer should be ignored or raise error
        # depending on DRF settings and serializer depth. For this primarily read-only serializer,
        # we're testing its output. Direct updates are not its purpose.
        serializer = UserSubscriptionSerializer(self.subscription, context={'request': self.request})
        for field_name in serializer.Meta.read_only_fields:
            if field_name in serializer.fields: # Check if field is actually exposed
                self.assertTrue(serializer.fields[field_name].read_only, f"{field_name} should be read-only")


class TransactionSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="transuser@example.com", password="password", full_name="Trans User")
        self.plan = SubscriptionPlan.objects.create(name="Trans Plan S", price=Decimal("1.00"))
        self.subscription = UserSubscription.objects.create(user=self.user, plan=self.plan, status='active')
        self.transaction = Transaction.objects.create(
            user=self.user,
            user_subscription=self.subscription,
            stripe_payment_intent_id="pi_transerializer",
            transaction_type="subscription_renewal",
            status="succeeded",
            amount=Decimal("1.00"),
            currency="USD",
            processed_at=timezone.now()
        )
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
        self.request.user = self.user # For context if any nested part needs it

    def test_transaction_serializer_output_data(self):
        """Test TransactionSerializer serializes data correctly."""
        serializer = TransactionSerializer(self.transaction, context={'request': self.request})
        data = serializer.data

        self.assertEqual(data['id'], str(self.transaction.id))
        self.assertEqual(data['user']['email'], self.user.email)
        # self.assertEqual(data['user_subscription']['id'], str(self.subscription.id)) # If full sub serialized
        self.assertEqual(data['stripe_payment_intent_id'], self.transaction.stripe_payment_intent_id)
        self.assertEqual(data['transaction_type'], "subscription_renewal")
        self.assertEqual(data['status'], "succeeded")
        self.assertEqual(Decimal(data['amount']), self.transaction.amount)
        self.assertIsNotNone(data['processed_at'])


class CreateSubscriptionCheckoutSessionSerializerTests(TestCase):
    def setUp(self):
        self.active_plan_with_stripe_id = SubscriptionPlan.objects.create(
            name="Checkout Active Plan", price=Decimal("10.00"), is_active=True, stripe_price_id="price_checkout_active"
        )
        self.inactive_plan = SubscriptionPlan.objects.create(
            name="Checkout Inactive Plan", price=Decimal("10.00"), is_active=False, stripe_price_id="price_checkout_inactive"
        )
        self.active_plan_no_stripe_id = SubscriptionPlan.objects.create(
            name="Checkout No StripeID Plan", price=Decimal("10.00"), is_active=True, stripe_price_id=None # No Stripe ID
        )
        self.valid_urls = {
            "success_url": "https://uplas.me/payment/success",
            "cancel_url": "https://uplas.me/payment/cancel",
        }

    def test_create_checkout_serializer_valid_data(self):
        """Test serializer is valid with correct plan_id and URLs."""
        data = {"plan_id": str(self.active_plan_with_stripe_id.id), **self.valid_urls}
        serializer = CreateSubscriptionCheckoutSessionSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['plan_id'], self.active_plan_with_stripe_id.id)

    def test_create_checkout_serializer_invalid_plan_id_non_existent(self):
        """Test serializer is invalid if plan_id does not exist."""
        non_existent_uuid = uuid.uuid4()
        data = {"plan_id": str(non_existent_uuid), **self.valid_urls}
        serializer = CreateSubscriptionCheckoutSessionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("plan_id", serializer.errors)
        self.assertIn("Invalid or inactive subscription plan ID.", str(serializer.errors['plan_id'][0]))


    def test_create_checkout_serializer_invalid_plan_id_inactive(self):
        """Test serializer is invalid if plan is inactive."""
        data = {"plan_id": str(self.inactive_plan.id), **self.valid_urls}
        serializer = CreateSubscriptionCheckoutSessionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("plan_id", serializer.errors)
        self.assertIn("Invalid or inactive subscription plan ID.", str(serializer.errors['plan_id'][0]))


    def test_create_checkout_serializer_invalid_plan_id_no_stripe_id(self):
        """Test serializer is invalid if plan has no stripe_price_id."""
        data = {"plan_id": str(self.active_plan_no_stripe_id.id), **self.valid_urls}
        serializer = CreateSubscriptionCheckoutSessionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("plan_id", serializer.errors)
        self.assertIn("This subscription plan is not configured for online payment.", str(serializer.errors['plan_id'][0]))


    def test_create_checkout_serializer_missing_success_url(self):
        """Test serializer is invalid if success_url is missing."""
        data = {"plan_id": str(self.active_plan_with_stripe_id.id), "cancel_url": self.valid_urls["cancel_url"]}
        serializer = CreateSubscriptionCheckoutSessionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("success_url", serializer.errors)

    def test_create_checkout_serializer_invalid_success_url(self):
        """Test serializer is invalid if success_url is not a valid URL."""
        data = {"plan_id": str(self.active_plan_with_stripe_id.id), **self.valid_urls, "success_url": "not-a-url"}
        serializer = CreateSubscriptionCheckoutSessionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("success_url", serializer.errors)
