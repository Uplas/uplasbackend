from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock # For mocking Stripe API calls

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.payments.models import (
    SubscriptionPlan, UserSubscription, PaymentTransaction
)
from apps.payments.serializers import (
    SubscriptionPlanSerializer, UserSubscriptionSerializer, PaymentTransactionSerializer
)
from django.conf import settings # For Stripe keys and webhook secret

User = get_user_model()

# Test Data Setup Mixin (adapted for APITestCase)
class PaymentsViewTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username='payview_admin', email='payview_admin@example.com', password='password123',
            full_name='PayView Admin'
        )
        cls.user1 = User.objects.create_user(
            username='payview_user1', email='payview_user1@example.com', password='password123',
            full_name='PayView User One'
        )
        # It's good practice to have a UserProfile if your User model expects one for stripe_customer_id
        # For simplicity, we'll assume stripe_customer_id can be directly on User or handled in view.
        # If UserProfile is used:
        # from apps.users.models import UserProfile # Assuming you have this
        # UserProfile.objects.create(user=cls.user1, stripe_customer_id='cus_test_payview_user1')


        cls.user2_no_sub = User.objects.create_user(
            username='payview_user2', email='payview_user2@example.com', password='password123',
            full_name='PayView User Two'
        )

        cls.plan_monthly_active = SubscriptionPlan.objects.create(
            name='Active Monthly Plan',
            stripe_price_id='price_active_monthly_pv',
            price=Decimal('29.99'),
            currency='USD',
            billing_cycle='monthly',
            is_active=True,
            display_order=1
        )
        cls.plan_annual_active = SubscriptionPlan.objects.create(
            name='Active Annual Plan',
            stripe_price_id='price_active_annual_pv',
            price=Decimal('299.00'),
            currency='USD',
            billing_cycle='annually',
            is_active=True,
            display_order=0
        )
        cls.plan_monthly_inactive = SubscriptionPlan.objects.create(
            name='Inactive Monthly Plan',
            stripe_price_id='price_inactive_monthly_pv',
            price=Decimal('15.00'),
            currency='USD',
            billing_cycle='monthly',
            is_active=False # Inactive
        )

        cls.user1_subscription = UserSubscription.objects.create(
            user=cls.user1,
            plan=cls.plan_monthly_active,
            stripe_subscription_id='sub_payview_user1_active',
            stripe_customer_id='cus_payview_user1', # Make sure this customer ID exists in Stripe for real tests, or mock it
            status='active',
            current_period_start=timezone.now() - timezone.timedelta(days=15),
            current_period_end=timezone.now() + timezone.timedelta(days=15)
        )

    def get_jwt_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {'refresh': str(refresh), 'access': str(refresh.access_token)}

    def authenticate_client_with_jwt(self, user):
        tokens = self.get_jwt_tokens_for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')


class SubscriptionPlanViewSetTests(PaymentsViewTestDataMixin, APITestCase):
    def test_list_active_subscription_plans_anonymous(self):
        url = reverse('payments:subscription-plan-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Only active plans should be listed (plan_monthly_active, plan_annual_active)
        self.assertEqual(len(response.data['results']), 2)
        plan_names_in_response = [plan['name'] for plan in response.data['results']]
        self.assertIn(self.plan_monthly_active.name, plan_names_in_response)
        self.assertIn(self.plan_annual_active.name, plan_names_in_response)
        self.assertNotIn(self.plan_monthly_inactive.name, plan_names_in_response)

    def test_retrieve_active_subscription_plan_anonymous(self):
        url = reverse('payments:subscription-plan-detail', kwargs={'pk': self.plan_monthly_active.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.plan_monthly_active.name)

    def test_retrieve_inactive_subscription_plan_anonymous_not_found(self):
        # ViewSet queryset filters for is_active=True
        url = reverse('payments:subscription-plan-detail', kwargs={'pk': self.plan_monthly_inactive.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Admin-only actions (create, update, delete) for plans are typically via Django Admin.
    # If API endpoints for these are added to the ViewSet, they'd need IsAdminUser permission
    # and corresponding tests. For a ReadOnlyModelViewSet, these are not applicable.


class UserSubscriptionViewSetTests(PaymentsViewTestDataMixin, APITestCase):
    def test_get_my_subscription_authenticated_user_has_sub(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('payments:user-subscription-my-subscription')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stripe_subscription_id'], self.user1_subscription.stripe_subscription_id)
        self.assertEqual(response.data['plan']['id'], str(self.plan_monthly_active.id))

    def test_get_my_subscription_authenticated_user_no_sub(self):
        self.authenticate_client_with_jwt(self.user2_no_sub)
        url = reverse('payments:user-subscription-my-subscription')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('No active subscription found', response.data['detail'])

    def test_get_my_subscription_unauthenticated(self):
        url = reverse('payments:user-subscription-my-subscription')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('stripe.Customer.create')
    @patch('stripe.PaymentMethod.attach')
    @patch('stripe.Customer.modify')
    @patch('stripe.Subscription.create')
    def test_create_subscription_success(
        self, mock_stripe_sub_create, mock_stripe_customer_modify,
        mock_stripe_pm_attach, mock_stripe_customer_create
    ):
        self.authenticate_client_with_jwt(self.user2_no_sub) # User without a subscription

        # Mock Stripe API responses
        mock_stripe_customer_create.return_value = MagicMock(id='cus_new_test_customer')
        # mock_stripe_pm_attach.return_value = MagicMock() # Attach doesn't return much
        # mock_stripe_customer_modify.return_value = MagicMock() # Modify doesn't return much

        # Simulate a successful subscription creation with a PaymentIntent that succeeded
        mock_stripe_sub_create.return_value = MagicMock(
            id='sub_new_test_subscription',
            status='active', # or 'trialing' or 'incomplete' if payment_intent is requires_action
            items={'data': [{'price': {'id': self.plan_annual_active.stripe_price_id}}]},
            current_period_start=int(timezone.now().timestamp()),
            current_period_end=int((timezone.now() + timezone.timedelta(days=30)).timestamp()),
            trial_start=None,
            trial_end=None,
            latest_invoice=MagicMock(
                id='in_new_test_invoice',
                payment_intent=MagicMock(
                    id='pi_new_test_payment_intent',
                    status='succeeded',
                    client_secret=None, # Not needed if succeeded
                    amount_received=int(self.plan_annual_active.price * 100),
                    currency=self.plan_annual_active.currency.lower(),
                    created=int(timezone.now().timestamp())
                )
            ),
            pending_setup_intent=None
        )

        url = reverse('payments:user-subscription-create-subscription')
        data = {
            'plan_id': str(self.plan_annual_active.id),
            'payment_method_id': 'pm_test_card_visa' # A test payment method ID from Stripe.js
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['stripe_subscription_id'], 'sub_new_test_subscription')
        self.assertEqual(response.data['status'], 'active')
        
        mock_stripe_customer_create.assert_called_once()
        mock_stripe_sub_create.assert_called_once()

        # Verify UserSubscription and PaymentTransaction created in DB
        self.assertTrue(UserSubscription.objects.filter(user=self.user2_no_sub, stripe_subscription_id='sub_new_test_subscription').exists())
        self.assertTrue(PaymentTransaction.objects.filter(user=self.user2_no_sub, stripe_charge_id='pi_new_test_payment_intent', status='succeeded').exists())

    @patch('stripe.Subscription.create')
    def test_create_subscription_user_already_has_active_sub(self, mock_stripe_sub_create):
        self.authenticate_client_with_jwt(self.user1) # user1 already has a subscription
        url = reverse('payments:user-subscription-create-subscription')
        data = {'plan_id': str(self.plan_annual_active.id), 'payment_method_id': 'pm_another_card'}
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already have an active subscription', response.data['detail'])
        mock_stripe_sub_create.assert_not_called()

    @patch('stripe.Subscription.delete')
    @patch('stripe.Subscription.modify')
    def test_cancel_subscription_at_period_end(self, mock_stripe_sub_modify, mock_stripe_sub_delete):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('payments:user-subscription-cancel-subscription')
        data = {'cancel_immediately': False} # Default, or explicitly False

        # Mock Stripe API response for modify
        mock_stripe_sub_modify.return_value = MagicMock(id=self.user1_subscription.stripe_subscription_id, cancel_at_period_end=True)

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('Subscription cancellation requested', response.data['detail'])
        
        mock_stripe_sub_modify.assert_called_once_with(
            self.user1_subscription.stripe_subscription_id,
            cancel_at_period_end=True
        )
        mock_stripe_sub_delete.assert_not_called()

        self.user1_subscription.refresh_from_db()
        self.assertTrue(self.user1_subscription.cancel_at_period_end)
        self.assertEqual(self.user1_subscription.status, 'pending_cancellation') # Local status update

    @patch('stripe.Subscription.delete')
    @patch('stripe.Subscription.modify')
    def test_cancel_subscription_immediately(self, mock_stripe_sub_modify, mock_stripe_sub_delete):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('payments:user-subscription-cancel-subscription')
        data = {'cancel_immediately': True}

        # Mock Stripe API response for delete
        mock_stripe_sub_delete.return_value = MagicMock(id=self.user1_subscription.stripe_subscription_id, status='canceled')

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        
        mock_stripe_sub_delete.assert_called_once_with(self.user1_subscription.stripe_subscription_id)
        mock_stripe_sub_modify.assert_not_called()
        # The actual status update to 'cancelled' in DB would typically happen via webhook 'customer.subscription.deleted'


class PaymentTransactionViewSetTests(PaymentsViewTestDataMixin, APITestCase):
    def setUp(self):
        super().setUpTestData() # Call mixin's setup
        self.transaction1_user1 = PaymentTransaction.objects.create(
            user=self.user1, user_subscription=self.user1_subscription,
            stripe_charge_id='ch_payview_user1_txn1', amount=Decimal('29.99'), currency='USD',
            status='succeeded', paid_at=timezone.now()
        )
        self.transaction2_user1 = PaymentTransaction.objects.create(
            user=self.user1, user_subscription=self.user1_subscription,
            stripe_charge_id='ch_payview_user1_txn2', amount=Decimal('29.99'), currency='USD',
            status='succeeded', paid_at=timezone.now() - timezone.timedelta(days=30)
        )
        # Transaction for another user, should not be visible to user1
        self.transaction_user2 = PaymentTransaction.objects.create(
            user=self.user2_no_sub, # No active sub, but could have past transactions
            stripe_charge_id='ch_payview_user2_txn1', amount=Decimal('10.00'), currency='USD',
            status='failed', created_at=timezone.now() - timezone.timedelta(days=5)
        )

    def test_list_my_payment_transactions(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('payments:payment-transaction-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # Only user1's transactions
        charge_ids_in_response = [item['stripe_charge_id'] for item in response.data['results']]
        self.assertIn(self.transaction1_user1.stripe_charge_id, charge_ids_in_response)
        self.assertIn(self.transaction2_user1.stripe_charge_id, charge_ids_in_response)
        self.assertNotIn(self.transaction_user2.stripe_charge_id, charge_ids_in_response)

    def test_retrieve_my_payment_transaction(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('payments:payment-transaction-detail', kwargs={'pk': self.transaction1_user1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stripe_charge_id'], self.transaction1_user1.stripe_charge_id)

    def test_retrieve_other_user_payment_transaction_not_found(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('payments:payment-transaction-detail', kwargs={'pk': self.transaction_user2.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # Due to queryset filtering

    def test_list_transactions_unauthenticated(self):
        url = reverse('payments:payment-transaction-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class StripeWebhookViewTests(PaymentsViewTestDataMixin, APITestCase):
    # These tests are more complex as they involve mocking Stripe's event construction
    # and verifying the side effects (database changes).

    @patch('stripe.Webhook.construct_event')
    def test_webhook_invoice_payment_succeeded(self, mock_construct_event):
        # Prepare a mock Stripe Event object
        stripe_sub_id = self.user1_subscription.stripe_subscription_id
        stripe_customer_id = self.user1_subscription.stripe_customer_id
        invoice_id = 'in_test_webhook_invoice'
        payment_intent_id = 'pi_test_webhook_pi'
        amount_paid = int(self.user1_subscription.plan.price * 100)
        currency = self.user1_subscription.plan.currency.lower()
        period_start_ts = int((self.user1_subscription.current_period_end + timezone.timedelta(seconds=1)).timestamp())
        period_end_ts = int((self.user1_subscription.current_period_end + timezone.timedelta(days=30)).timestamp())
        paid_at_ts = period_start_ts # Simulate payment at start of new period

        mock_event_data = {
            'id': 'evt_test_webhook_event',
            'type': 'invoice.payment_succeeded',
            'data': {
                'object': {
                    'id': invoice_id,
                    'object': 'invoice',
                    'customer': stripe_customer_id,
                    'subscription': stripe_sub_id,
                    'payment_intent': payment_intent_id,
                    'charge': 'ch_dummy_charge_for_pi', # Can be same as PI or a related charge
                    'amount_paid': amount_paid,
                    'amount_due': amount_paid, # For succeeded
                    'currency': currency,
                    'period_start': period_start_ts,
                    'period_end': period_end_ts,
                    'status_transitions': {'paid_at': paid_at_ts},
                    'payment_settings': {'payment_method_types': ['card']},
                    'number': 'INV-123-WEBHOOK'
                }
            }
        }
        mock_construct_event.return_value = mock_event_data # Stripe library usually returns an Event object, here simplified to dict

        url = reverse('payments:stripe-webhook')
        # Stripe sends a signature, which we are mocking the verification of.
        # The actual signature depends on the payload and your webhook secret.
        # For testing, we bypass the actual signature check by mocking construct_event.
        response = self.client.post(
            url,
            data=mock_event_data, # This is a simplification, actual payload is raw body
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='whsec_test_signature_is_mocked' # Dummy signature
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        mock_construct_event.assert_called_once() # Ensure our mock was used

        # Verify database changes
        self.user1_subscription.refresh_from_db()
        self.assertEqual(self.user1_subscription.status, 'active')
        self.assertEqual(int(self.user1_subscription.current_period_start.timestamp()), period_start_ts)
        self.assertEqual(int(self.user1_subscription.current_period_end.timestamp()), period_end_ts)

        self.assertTrue(PaymentTransaction.objects.filter(
            user=self.user1,
            stripe_charge_id=payment_intent_id, # or invoice.charge
            stripe_invoice_id=invoice_id,
            status='succeeded'
        ).exists())

    @patch('stripe.Webhook.construct_event')
    def test_webhook_customer_subscription_deleted(self, mock_construct_event):
        stripe_sub_id = self.user1_subscription.stripe_subscription_id
        canceled_at_ts = int(timezone.now().timestamp())

        mock_event_data = {
            'id': 'evt_test_sub_deleted_event',
            'type': 'customer.subscription.deleted',
            'data': {
                'object': {
                    'id': stripe_sub_id,
                    'object': 'subscription',
                    'status': 'canceled', # Stripe sends 'canceled' on delete
                    'customer': self.user1_subscription.stripe_customer_id,
                    'current_period_start': int(self.user1_subscription.current_period_start.timestamp()),
                    'current_period_end': int(self.user1_subscription.current_period_end.timestamp()), # Might be old period end
                    'canceled_at': canceled_at_ts,
                    'items': {'data': [{'price': {'id': self.user1_subscription.plan.stripe_price_id}}]}
                }
            }
        }
        mock_construct_event.return_value = mock_event_data

        url = reverse('payments:stripe-webhook')
        response = self.client.post(
            url, data=mock_event_data, content_type='application/json',
            HTTP_STRIPE_SIGNATURE='whsec_test_sig_mocked_delete'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user1_subscription.refresh_from_db()
        self.assertEqual(self.user1_subscription.status, 'cancelled')
        self.assertEqual(int(self.user1_subscription.cancelled_at.timestamp()), canceled_at_ts)

    def test_webhook_invalid_signature(self):
        # No need to mock construct_event here, we want it to fail
        url = reverse('payments:stripe-webhook')
        response = self.client.post(
            url,
            data={"id": "evt_bad_sig", "type": "test"}, # Actual payload
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='whsec_invalid_signature' # This signature won't match
        )
        # This relies on stripe.Webhook.construct_event raising SignatureVerificationError
        # which our view catches and returns 400.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid signature', response.data.get('error', '').lower())


# TODO: Add more tests for:
# - StripeWebhookView:
#   - invoice.payment_failed
#   - customer.subscription.updated (plan changes, trial ending soon handling)
#   - checkout.session.completed (if using Stripe Checkout)
#   - Other important Stripe events you handle.
#   - Idempotency if you implement explicit checks (Stripe handles retries well though).
# - UserSubscriptionViewSet:
#   - create_subscription with PaymentIntent requires_action flow.
#   - create_subscription with trial periods.
#   - cancel_subscription when already cancelled or no subscription exists.
#   - (If added) create_billing_portal_session action.
# - Permissions for all actions on all ViewSets with different user types.
# - Error handling for Stripe API errors (e.g., card declined).
