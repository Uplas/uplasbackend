from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from uuid import uuid4

from rest_framework.test import APIRequestFactory # For providing request context
from rest_framework.exceptions import ValidationError

from apps.payments.models import (
    SubscriptionPlan, UserSubscription, PaymentTransaction
)
from apps.payments.serializers import (
    SubscriptionPlanSerializer,
    UserSubscriptionSerializer,
    CreateSubscriptionSerializer,
    CancelSubscriptionSerializer,
    PaymentTransactionSerializer,
    StripeWebhookEventSerializer, # For basic structure validation
    SimpleUserSerializer
)
from django.conf import settings

User = get_user_model()

# Test Data Setup Mixin (adapted for serializer tests)
class PaymentsSerializerTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user1 = User.objects.create_user(
            username='payser_user1', email='payser_user1@example.com',
            password='password123', full_name='PaySer User One'
        )
        cls.user2 = User.objects.create_user(
            username='payser_user2', email='payser_user2@example.com',
            password='password123', full_name='PaySer User Two'
        )
        # Mock admin user for serializers that might have admin-specific behavior if tested here
        cls.admin_user = User.objects.create_superuser(
            username='payser_admin', email='payser_admin@example.com',
            password='password123', full_name='PaySer Admin'
        )


        cls.plan_monthly = SubscriptionPlan.objects.create(
            name='Monthly Gold Plan',
            stripe_price_id='price_gold_monthly_ser_test',
            price=Decimal('19.99'),
            currency='USD',
            billing_cycle='monthly',
            features={'streaming_quality': '1080p', 'devices': 2},
            is_active=True,
            display_order=1
        )
        cls.plan_annually_inactive = SubscriptionPlan.objects.create(
            name='Annual Silver Plan (Inactive)',
            stripe_price_id='price_silver_annual_ser_test_inactive',
            price=Decimal('150.00'),
            currency='USD',
            billing_cycle='annually',
            is_active=False, # Inactive
            display_order=0
        )

        cls.user1_subscription = UserSubscription.objects.create(
            user=cls.user1,
            plan=cls.plan_monthly,
            stripe_subscription_id='sub_ser_user1_monthly',
            stripe_customer_id='cus_ser_user1',
            status='active',
            current_period_start=timezone.now() - timezone.timedelta(days=5),
            current_period_end=timezone.now() + timezone.timedelta(days=25)
        )

        # For providing request context to serializers
        cls.factory = APIRequestFactory()
        # Mock request that can be passed in serializer context
        cls.request_user1 = cls.factory.get('/fake-endpoint')
        cls.request_user1.user = cls.user1

        cls.request_user2 = cls.factory.get('/fake-endpoint')
        cls.request_user2.user = cls.user2


class SubscriptionPlanSerializerTests(PaymentsSerializerTestDataMixin, TestCase):
    def test_serialization_output(self):
        serializer = SubscriptionPlanSerializer(instance=self.plan_monthly)
        data = serializer.data
        self.assertEqual(data['name'], self.plan_monthly.name)
        self.assertEqual(data['stripe_price_id'], self.plan_monthly.stripe_price_id)
        self.assertEqual(Decimal(data['price']), self.plan_monthly.price)
        self.assertEqual(data['currency_display'], dict(settings.CURRENCY_CHOICES).get(self.plan_monthly.currency))
        self.assertEqual(data['billing_cycle_display'], dict(self.plan_monthly._meta.get_field('billing_cycle').choices).get(self.plan_monthly.billing_cycle))
        self.assertTrue(data['is_active'])
        self.assertEqual(data['features']['devices'], 2)

    def test_deserialization_create_valid(self):
        data = {
            "name": "Test Pro Plan",
            "stripe_price_id": "price_test_pro_ser",
            "price": "29.99",
            "currency": "USD",
            "billing_cycle": "monthly",
            "features": {"downloads": True},
            "is_active": True,
            "display_order": 3
        }
        serializer = SubscriptionPlanSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        plan = serializer.save()
        self.assertEqual(plan.name, "Test Pro Plan")
        self.assertEqual(plan.stripe_price_id, "price_test_pro_ser")

    def test_deserialization_invalid_stripe_price_id_format(self):
        data = {"name": "Invalid Plan", "stripe_price_id": "invalid_id_format", "price": "10.00"}
        serializer = SubscriptionPlanSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('stripe_price_id', serializer.errors)
        self.assertIn("Invalid Stripe Price ID format", str(serializer.errors['stripe_price_id']))

    def test_deserialization_update(self):
        data = {"name": "Basic Monthly Updated", "price": "10.99"}
        serializer = SubscriptionPlanSerializer(instance=self.plan_monthly, data=data, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        plan = serializer.save()
        self.assertEqual(plan.name, "Basic Monthly Updated")
        self.assertEqual(plan.price, Decimal("10.99"))


class UserSubscriptionSerializerTests(PaymentsSerializerTestDataMixin, TestCase):
    def test_serialization_output(self):
        serializer = UserSubscriptionSerializer(instance=self.user1_subscription, context={'request': self.request_user1})
        data = serializer.data
        self.assertEqual(data['id'], str(self.user1_subscription.id))
        self.assertEqual(data['user']['email'], self.user1.email)
        self.assertEqual(data['plan']['name'], self.plan_monthly.name)
        self.assertEqual(data['stripe_subscription_id'], self.user1_subscription.stripe_subscription_id)
        self.assertEqual(data['status'], 'active')
        self.assertTrue(data['is_active_property']) # from model property
        self.assertIsNotNone(data['current_period_end'])

    def test_deserialization_create_with_plan_id(self):
        # Note: UserSubscription creation is complex and usually tied to Stripe API calls in views.
        # This test focuses on the serializer's ability to accept plan_id if used directly.
        # The main validation for preventing duplicate subscriptions is also tested.
        data = {
            "plan_id": str(self.plan_monthly.id),
            # stripe_subscription_id, stripe_customer_id, status etc. are read_only or set by backend
        }
        # User2 does not have a subscription yet.
        serializer = UserSubscriptionSerializer(data=data, context={'request': self.request_user2})
        
        # We expect validation error if user already has a subscription (due to OneToOne field)
        # Let's test the case where user1 tries to create another one (should fail in validate)
        serializer_user1_fail = UserSubscriptionSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer_user1_fail.is_valid())
        self.assertIn('non_field_errors', serializer_user1_fail.errors) # Or specific error from validate
        self.assertIn("User already has an active subscription.", str(serializer_user1_fail.errors['non_field_errors']))

        # For user2 (no existing sub), if we were to call save, it would need more fields
        # or the create method to handle it. This serializer is mostly for READ.
        # The `CreateSubscriptionSerializer` is for initiating creation.
        # If we were to make this writable, we'd need to mock more.
        # For now, let's assume this serializer is primarily for output and plan_id is for input if used.
        # This test primarily checks the duplicate validation.

    def test_read_only_fields_not_writable(self):
        data = {
            "plan_id": str(self.plan_monthly.id),
            "stripe_subscription_id": "sub_new_attempt_write", # Read-only
            "status": "trialing" # Read-only
        }
        serializer = UserSubscriptionSerializer(instance=self.user1_subscription, data=data, partial=True, context={'request': self.request_user1})
        self.assertTrue(serializer.is_valid()) # It will be valid, but read-only fields won't be changed by save()
        sub = serializer.save()
        self.assertNotEqual(sub.stripe_subscription_id, "sub_new_attempt_write")
        self.assertNotEqual(sub.status, "trialing") # Status should not change via direct serialization here


class CreateSubscriptionSerializerTests(PaymentsSerializerTestDataMixin, TestCase):
    def test_valid_data(self):
        data = {
            "plan_id": str(self.plan_monthly.id),
            "payment_method_id": "pm_test_valid123"
        }
        serializer = CreateSubscriptionSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['plan_id'], self.plan_monthly) # Validated to be the object
        self.assertEqual(serializer.validated_data['payment_method_id'], "pm_test_valid123")

    def test_invalid_plan_id_uuid_format(self):
        data = {"plan_id": "not-a-uuid", "payment_method_id": "pm_test"}
        serializer = CreateSubscriptionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('plan_id', serializer.errors)

    def test_non_existent_plan_id(self):
        non_existent_uuid = str(uuid4())
        data = {"plan_id": non_existent_uuid, "payment_method_id": "pm_test"}
        serializer = CreateSubscriptionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('plan_id', serializer.errors)
        self.assertIn("Invalid or inactive subscription plan ID.", str(serializer.errors['plan_id']))

    def test_inactive_plan_id(self):
        data = {"plan_id": str(self.plan_annually_inactive.id), "payment_method_id": "pm_test"}
        serializer = CreateSubscriptionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('plan_id', serializer.errors)
        self.assertIn("Invalid or inactive subscription plan ID.", str(serializer.errors['plan_id']))

    def test_invalid_payment_method_id_format(self):
        data = {"plan_id": str(self.plan_monthly.id), "payment_method_id": "invalid_pm_format"}
        serializer = CreateSubscriptionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('payment_method_id', serializer.errors)
        self.assertIn("Invalid Stripe PaymentMethod ID format.", str(serializer.errors['payment_method_id']))


class CancelSubscriptionSerializerTests(PaymentsSerializerTestDataMixin, TestCase):
    def test_valid_data_default(self):
        data = {} # cancel_immediately defaults to False
        serializer = CancelSubscriptionSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertFalse(serializer.validated_data['cancel_immediately'])

    def test_valid_data_cancel_immediately_true(self):
        data = {"cancel_immediately": True}
        serializer = CancelSubscriptionSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertTrue(serializer.validated_data['cancel_immediately'])

    def test_valid_data_cancel_immediately_false(self):
        data = {"cancel_immediately": False}
        serializer = CancelSubscriptionSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertFalse(serializer.validated_data['cancel_immediately'])

    def test_invalid_data_type_for_cancel_immediately(self):
        data = {"cancel_immediately": "not-a-boolean"}
        serializer = CancelSubscriptionSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('cancel_immediately', serializer.errors)


class PaymentTransactionSerializerTests(PaymentsSerializerTestDataMixin, TestCase):
    def setUp(self):
        super().setUpTestData() # Call mixin's setup
        self.transaction = PaymentTransaction.objects.create(
            user=self.user1,
            user_subscription=self.user1_subscription,
            stripe_charge_id='ch_ser_test_txn1',
            amount=self.plan_monthly.price,
            currency=self.plan_monthly.currency,
            status='succeeded',
            paid_at=timezone.now(),
            description="Test Transaction Serialization"
        )

    def test_serialization_output(self):
        serializer = PaymentTransactionSerializer(instance=self.transaction)
        data = serializer.data
        self.assertEqual(data['id'], str(self.transaction.id))
        self.assertEqual(data['user']['email'], self.user1.email)
        self.assertEqual(data['user_subscription_id'], str(self.user1_subscription.id))
        self.assertEqual(data['stripe_charge_id'], self.transaction.stripe_charge_id)
        self.assertEqual(Decimal(data['amount']), self.transaction.amount)
        self.assertEqual(data['currency_display'], dict(settings.CURRENCY_CHOICES).get(self.transaction.currency))
        self.assertEqual(data['status'], 'succeeded')
        self.assertEqual(data['status_display'], dict(PAYMENT_STATUS_CHOICES).get('succeeded'))
        self.assertIsNotNone(data['paid_at'])

    def test_all_fields_are_read_only(self):
        # Attempt to update a "read-only" field
        data = {"amount": "1000.00"} # Amount is in read_only_fields
        serializer = PaymentTransactionSerializer(instance=self.transaction, data=data, partial=True)
        self.assertTrue(serializer.is_valid()) # Serializer is valid as it ignores read-only fields on input
        updated_transaction = serializer.save()
        self.assertNotEqual(updated_transaction.amount, Decimal("1000.00")) # Should not change
        self.assertEqual(updated_transaction.amount, self.transaction.amount) # Stays the same


class StripeWebhookEventSerializerTests(PaymentsSerializerTestDataMixin, TestCase):
    def test_valid_stripe_event_structure(self):
        event_data = {
            "id": "evt_test_webhook123",
            "type": "invoice.payment_succeeded",
            "api_version": "2020-08-27",
            "created": 1670000000,
            "data": {"object": {"id": "in_test_invoice123", "amount_paid": 1999, "currency": "usd"}},
            "livemode": False,
            "pending_webhooks": 0,
            "request": {"id": "req_test123", "idempotency_key": None}
        }
        serializer = StripeWebhookEventSerializer(data=event_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['id'], "evt_test_webhook123")
        self.assertEqual(serializer.validated_data['type'], "invoice.payment_succeeded")
        self.assertIsInstance(serializer.validated_data['data'], dict)

    def test_missing_required_field_id(self):
        event_data = {
            # "id": "evt_test_webhook123", # Missing ID
            "type": "invoice.payment_succeeded",
            "api_version": "2020-08-27",
            "created": 1670000000,
            "data": {"object": {}},
            "livemode": False,
            "pending_webhooks": 0,
            "request": None
        }
        serializer = StripeWebhookEventSerializer(data=event_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('id', serializer.errors)

    def test_missing_required_field_type(self):
        event_data = {
            "id": "evt_test_webhook123",
            # "type": "invoice.payment_succeeded", # Missing type
            "api_version": "2020-08-27",
            "created": 1670000000,
            "data": {"object": {}},
            "livemode": False,
            "pending_webhooks": 0,
            "request": None
        }
        serializer = StripeWebhookEventSerializer(data=event_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('type', serializer.errors)

