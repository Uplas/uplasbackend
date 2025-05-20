from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from unittest.mock import patch, MagicMock # For mocking Stripe API calls
import json # For webhook payload simulation

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import SubscriptionPlan, UserSubscription, Transaction
# from apps.users.models import UserProfile # Ensure UserProfile is created by signal if needed

User = get_user_model()

# Dummy Stripe IDs for mocking
MOCK_STRIPE_CUSTOMER_ID = "cus_mockcustomer123"
MOCK_STRIPE_SUBSCRIPTION_ID = "sub_mocksubscription123"
MOCK_STRIPE_CHECKOUT_SESSION_ID = "cs_test_mocksession123"
MOCK_STRIPE_PAYMENT_INTENT_ID = "pi_mockpaymentintent123"
MOCK_STRIPE_INVOICE_ID = "in_mockinvoice123"
MOCK_STRIPE_CHARGE_ID = "ch_mockcharge123"


class SubscriptionPlanViewSetTests(APITestCase):
    def setUp(self):
        self.plan1 = SubscriptionPlan.objects.create(name="Basic", price=Decimal("9.99"), is_active=True, stripe_price_id="price_basic")
        self.plan2 = SubscriptionPlan.objects.create(name="Premium", price=Decimal("19.99"), is_active=True, stripe_price_id="price_premium")
        SubscriptionPlan.objects.create(name="Inactive", price=Decimal("5.00"), is_active=False, stripe_price_id="price_inactive")
        self.list_url = reverse('payments:subscriptionplan-list')

    def test_list_subscription_plans(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # Only active plans
        plan_names = {item['name'] for item in response.data['results']}
        self.assertIn(self.plan1.name, plan_names)
        self.assertIn(self.plan2.name, plan_names)


class UserSubscriptionViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="subview@example.com", password="password", stripe_customer_id=MOCK_STRIPE_CUSTOMER_ID)
        self.plan = SubscriptionPlan.objects.create(name="Active Plan", price=Decimal("10.00"), stripe_price_id="price_active_subview")
        self.my_subscription_url = reverse('payments:my-usersubscription-list') # For GET (list action acts as retrieve)
        self.cancel_action_url = reverse('payments:my-usersubscription-cancel-my-subscription') # For POST to custom action

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_my_subscription_exists(self):
        UserSubscription.objects.create(
            user=self.user, plan=self.plan, status='active', stripe_subscription_id="sub_test_exists"
        )
        response = self.client.get(self.my_subscription_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['plan']['name'], self.plan.name)
        self.assertEqual(response.data['status'], 'active')

    def test_get_my_subscription_not_exists(self):
        response = self.client.get(self.my_subscription_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('stripe.Subscription.modify')
    def test_cancel_my_stripe_subscription_success(self, mock_stripe_sub_modify):
        """Test canceling an active Stripe-managed subscription."""
        mock_stripe_sub_modify.return_value = MagicMock(id=MOCK_STRIPE_SUBSCRIPTION_ID, cancel_at_period_end=True)
        user_sub = UserSubscription.objects.create(
            user=self.user, plan=self.plan, status='active', stripe_subscription_id=MOCK_STRIPE_SUBSCRIPTION_ID
        )
        response = self.client.post(self.cancel_action_url) # POST to the custom action
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("cancel at the end of the current billing period", response.data['detail'])
        user_sub.refresh_from_db()
        self.assertTrue(user_sub.cancel_at_period_end)
        mock_stripe_sub_modify.assert_called_once_with(MOCK_STRIPE_SUBSCRIPTION_ID, cancel_at_period_end=True)

    def test_cancel_my_internal_subscription_success(self):
        """Test canceling an internal (non-Stripe) subscription."""
        user_sub = UserSubscription.objects.create(user=self.user, plan=self.plan, status='active', stripe_subscription_id=None) # No Stripe ID
        response = self.client.post(self.cancel_action_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['detail'], 'Subscription marked as canceled internally.')
        user_sub.refresh_from_db()
        self.assertEqual(user_sub.status, 'canceled')
        self.assertIsNotNone(user_sub.canceled_at)
        self.assertIsNotNone(user_sub.ended_at)


    def test_cancel_my_subscription_no_active_sub(self):
        response = self.client.post(self.cancel_action_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('stripe.Subscription.modify')
    def test_cancel_my_stripe_subscription_stripe_error(self, mock_stripe_sub_modify):
        mock_stripe_sub_modify.side_effect = stripe.error.StripeError("Stripe API unavailable")
        UserSubscription.objects.create(
            user=self.user, plan=self.plan, status='active', stripe_subscription_id=MOCK_STRIPE_SUBSCRIPTION_ID
        )
        response = self.client.post(self.cancel_action_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Could not request cancellation", response.data['detail'])


class TransactionViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="transview@example.com", password="password")
        self.other_user = User.objects.create_user(email="othertrans@example.com", password="password")
        Transaction.objects.create(user=self.user, amount=Decimal("10.00"), currency="USD", status="succeeded")
        Transaction.objects.create(user=self.user, amount=Decimal("5.00"), currency="USD", status="failed")
        Transaction.objects.create(user=self.other_user, amount=Decimal("20.00"), currency="USD", status="succeeded")
        
        self.list_url = reverse('payments:transaction-list')
        self.client.force_authenticate(user=self.user)

    def test_list_my_transactions(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # Only self.user's transactions

    def test_list_transactions_unauthenticated(self):
        self.client.logout()
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CreateCheckoutSessionViewTests(APITestCase):
    def setUp(self):
        self.user_no_stripe_id = User.objects.create_user(email="checkout_no_id@example.com", password="password", full_name="Checkout User NoSID")
        self.user_with_stripe_id = User.objects.create_user(email="checkout_with_id@example.com", password="password", full_name="Checkout User SID", stripe_customer_id=MOCK_STRIPE_CUSTOMER_ID)
        self.plan = SubscriptionPlan.objects.create(name="Checkout Plan", price=Decimal("25.00"), is_active=True, stripe_price_id="price_checkout123")
        self.url = reverse('payments:create-checkout-session')
        self.client = APIClient()
        self.valid_payload = {
            "plan_id": str(self.plan.id),
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel"
        }

    @patch('stripe.Customer.create')
    @patch('stripe.checkout.Session.create')
    def test_create_checkout_session_new_stripe_customer(self, mock_checkout_session_create, mock_customer_create):
        """Test session creation when user is new to Stripe."""
        self.client.force_authenticate(user=self.user_no_stripe_id)
        mock_customer_create.return_value = MagicMock(id=MOCK_STRIPE_CUSTOMER_ID)
        mock_checkout_session_create.return_value = MagicMock(id=MOCK_STRIPE_CHECKOUT_SESSION_ID, url="https://stripe.com/checkout/mock_url")

        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("checkout_url", response.data)
        self.assertEqual(response.data["checkout_session_id"], MOCK_STRIPE_CHECKOUT_SESSION_ID)

        mock_customer_create.assert_called_once()
        self.user_no_stripe_id.refresh_from_db()
        self.assertEqual(self.user_no_stripe_id.stripe_customer_id, MOCK_STRIPE_CUSTOMER_ID)
        
        mock_checkout_session_create.assert_called_once_with(
            customer=MOCK_STRIPE_CUSTOMER_ID,
            payment_method_types=['card'],
            line_items=[{'price': self.plan.stripe_price_id, 'quantity': 1}],
            mode='subscription',
            success_url=self.valid_payload["success_url"] + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=self.valid_payload["cancel_url"],
            metadata={'uplas_user_id': str(self.user_no_stripe_id.id), 'uplas_plan_id': str(self.plan.id)}
        )
        self.assertTrue(UserSubscription.objects.filter(user=self.user_no_stripe_id, plan=self.plan, status='incomplete').exists())


    @patch('stripe.checkout.Session.create')
    def test_create_checkout_session_existing_stripe_customer(self, mock_checkout_session_create):
        """Test session creation when user already has a Stripe customer ID."""
        self.client.force_authenticate(user=self.user_with_stripe_id)
        mock_checkout_session_create.return_value = MagicMock(id=MOCK_STRIPE_CHECKOUT_SESSION_ID, url="https://stripe.com/checkout/mock_url")

        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_checkout_session_create.assert_called_once_with(
            customer=self.user_with_stripe_id.stripe_customer_id, # Existing ID used
            payment_method_types=['card'],
            line_items=[{'price': self.plan.stripe_price_id, 'quantity': 1}],
            mode='subscription',
            success_url=self.valid_payload["success_url"] + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=self.valid_payload["cancel_url"],
            metadata={'uplas_user_id': str(self.user_with_stripe_id.id), 'uplas_plan_id': str(self.plan.id)}
        )
        self.assertTrue(UserSubscription.objects.filter(user=self.user_with_stripe_id, plan=self.plan, status='incomplete').exists())


    def test_create_checkout_session_unauthenticated(self):
        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_checkout_session_invalid_plan_id(self):
        self.client.force_authenticate(user=self.user_no_stripe_id)
        payload = self.valid_payload.copy()
        payload["plan_id"] = str(uuid.uuid4()) # Non-existent plan
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # Serializer validation


class StripeWebhookViewTests(APITestCase):
    def setUp(self):
        self.webhook_url = reverse('payments:stripe-webhook')
        self.user = User.objects.create_user(email="webhookuser@example.com", password="password", stripe_customer_id=MOCK_STRIPE_CUSTOMER_ID)
        self.plan = SubscriptionPlan.objects.create(name="Webhook Plan", price=Decimal("30.00"), stripe_price_id="price_webhook_plan")
        
        # Mock settings value for webhook secret
        self.original_webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET_PAYMENTS', None)
        settings.STRIPE_WEBHOOK_SECRET_PAYMENTS = "whsec_test_mocksecretfordjangotests"
        # Also need to re-assign in view's module scope if it's loaded at import time
        # This is tricky. For robust testing of webhooks, stripe-mock is better.
        # For now, we rely on mocking construct_event.

    def tearDown(self):
        # Restore original webhook secret
        settings.STRIPE_WEBHOOK_SECRET_PAYMENTS = self.original_webhook_secret


    @patch('stripe.Webhook.construct_event')
    def test_webhook_checkout_session_completed_paid(self, mock_construct_event):
        """Test handler for checkout.session.completed with payment_status='paid'."""
        event_payload = {
            "id": "evt_mock_checkout_completed",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": MOCK_STRIPE_CHECKOUT_SESSION_ID,
                    "customer": MOCK_STRIPE_CUSTOMER_ID,
                    "subscription": MOCK_STRIPE_SUBSCRIPTION_ID,
                    "payment_status": "paid",
                    "metadata": {
                        "uplas_user_id": str(self.user.id),
                        "uplas_plan_id": str(self.plan.id)
                    }
                }
            }
        }
        mock_construct_event.return_value = event_payload # Return the dict itself, StripeObject is complex to mock fully

        # Simulate a preliminary incomplete subscription from CreateCheckoutSessionView
        UserSubscription.objects.create(user=self.user, plan=self.plan, status='incomplete', stripe_customer_id=MOCK_STRIPE_CUSTOMER_ID)

        response = self.client.post(
            self.webhook_url, 
            data=json.dumps(event_payload), # Send as raw JSON string
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE="t=123,v1=mockedsig" # Mocked signature
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        
        user_sub = UserSubscription.objects.get(user=self.user)
        # The status 'active' and period dates are typically set by customer.subscription.created/updated.
        # checkout.session.completed confirms payment and links sub_id.
        self.assertEqual(user_sub.stripe_subscription_id, MOCK_STRIPE_SUBSCRIPTION_ID)
        # self.assertEqual(user_sub.status, 'active') # This might not be set by checkout.session.completed alone

    @patch('stripe.Webhook.construct_event')
    def test_webhook_customer_subscription_created(self, mock_construct_event):
        """Test handler for customer.subscription.created."""
        stripe_sub_payload = {
            "id": MOCK_STRIPE_SUBSCRIPTION_ID,
            "customer": MOCK_STRIPE_CUSTOMER_ID,
            "status": "active",
            "current_period_start": int(timezone.now().timestamp()),
            "current_period_end": int((timezone.now() + timezone.timedelta(days=30)).timestamp()),
            "start_date": int(timezone.now().timestamp()),
            "items": {"data": [{"price": {"id": self.plan.stripe_price_id}}]},
            "cancel_at_period_end": False,
        }
        event_payload = {"id": "evt_mock_sub_created", "type": "customer.subscription.created", "data": {"object": stripe_sub_payload}}
        mock_construct_event.return_value = event_payload

        response = self.client.post(self.webhook_url, data=json.dumps(event_payload), content_type='application/json', HTTP_STRIPE_SIGNATURE="t=123,v1=mock")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        user_sub = UserSubscription.objects.get(user=self.user, stripe_subscription_id=MOCK_STRIPE_SUBSCRIPTION_ID)
        self.assertEqual(user_sub.status, "active")
        self.assertEqual(user_sub.plan, self.plan)
        self.assertIsNotNone(user_sub.current_period_end)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_premium_subscriber)
        self.assertEqual(self.user.subscription_plan_name, self.plan.name)


    @patch('stripe.Webhook.construct_event')
    def test_webhook_customer_subscription_deleted_canceled(self, mock_construct_event):
        """Test handler for customer.subscription.deleted (canceled)."""
        UserSubscription.objects.create(
            user=self.user, plan=self.plan, status='active', 
            stripe_subscription_id=MOCK_STRIPE_SUBSCRIPTION_ID,
            current_period_end=timezone.now() + timezone.timedelta(days=5) # Still active initially
        )
        self.user.is_premium_subscriber = True # Simulate active state
        self.user.save()

        canceled_at_ts = int(timezone.now().timestamp())
        stripe_sub_payload = {
            "id": MOCK_STRIPE_SUBSCRIPTION_ID,
            "customer": MOCK_STRIPE_CUSTOMER_ID,
            "status": "canceled", # Stripe sends 'canceled' status
            "current_period_start": int((timezone.now() - timezone.timedelta(days=25)).timestamp()),
            "current_period_end": int(timezone.now().timestamp()), # Period effectively ends now
            "canceled_at": canceled_at_ts,
            "items": {"data": [{"price": {"id": self.plan.stripe_price_id}}]},
            "cancel_at_period_end": False, # It's fully canceled now
        }
        event_payload = {"id": "evt_mock_sub_deleted", "type": "customer.subscription.deleted", "data": {"object": stripe_sub_payload}}
        mock_construct_event.return_value = event_payload

        response = self.client.post(self.webhook_url, data=json.dumps(event_payload), content_type='application/json', HTTP_STRIPE_SIGNATURE="t=123,v1=mock")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        user_sub = UserSubscription.objects.get(user=self.user, stripe_subscription_id=MOCK_STRIPE_SUBSCRIPTION_ID)
        self.assertEqual(user_sub.status, "canceled")
        self.assertEqual(user_sub.canceled_at, datetime.fromtimestamp(canceled_at_ts, tz=timezone.utc))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_premium_subscriber)

    @patch('stripe.Webhook.construct_event')
    def test_webhook_invoice_payment_succeeded(self, mock_construct_event):
        """Test handler for invoice.payment_succeeded."""
        UserSubscription.objects.create( # Ensure subscription exists for renewal invoice
            user=self.user, plan=self.plan, status='active', stripe_subscription_id=MOCK_STRIPE_SUBSCRIPTION_ID
        )
        invoice_payload = {
            "id": MOCK_STRIPE_INVOICE_ID,
            "customer": MOCK_STRIPE_CUSTOMER_ID,
            "subscription": MOCK_STRIPE_SUBSCRIPTION_ID,
            "payment_intent": MOCK_STRIPE_PAYMENT_INTENT_ID,
            "charge": MOCK_STRIPE_CHARGE_ID,
            "amount_paid": 3000, # Cents
            "currency": "usd",
            "billing_reason": "subscription_cycle", # For renewal
            "status_transitions": {"paid_at": int(timezone.now().timestamp())}
        }
        event_payload = {"id": "evt_mock_invoice_paid", "type": "invoice.payment_succeeded", "data": {"object": invoice_payload}}
        mock_construct_event.return_value = event_payload

        response = self.client.post(self.webhook_url, data=json.dumps(event_payload), content_type='application/json', HTTP_STRIPE_SIGNATURE="t=123,v1=mock")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        
        self.assertTrue(Transaction.objects.filter(
            user=self.user, 
            stripe_invoice_id=MOCK_STRIPE_INVOICE_ID,
            stripe_payment_intent_id=MOCK_STRIPE_PAYMENT_INTENT_ID,
            status='succeeded',
            amount=Decimal("30.00")
        ).exists())

    def test_webhook_invalid_signature(self):
        """Test webhook view returns 400 for invalid signature if construct_event is not mocked to succeed."""
        # This test relies on Stripe SDK raising SignatureVerificationError if secret is wrong
        # For a more direct test, mock construct_event to raise it.
        with patch('stripe.Webhook.construct_event', side_effect=stripe.error.SignatureVerificationError("Bad sig", "sig_header")):
            response = self.client.post(
                self.webhook_url,
                data=json.dumps({"id": "evt_test", "type": "test.event"}),
                content_type='application/json',
                HTTP_STRIPE_SIGNATURE="t=123,v1=badsignature"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("Invalid signature", response.data['error'])

    # More webhook tests:
    # - invoice.payment_failed
    # - Different subscription statuses (trialing, past_due, unpaid)
    # - Idempotency (processing same event ID twice) - requires more setup
