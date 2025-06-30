from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from unittest.mock import patch # For mocking external calls like WhatsApp sending

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import UserProfile
# Import serializers to compare response data or for setup if needed
from apps.users.serializers import UserSerializer, UserProfileSerializer 

User = get_user_model()

# Test Data Setup Mixin (adapted for APITestCase)
class UsersViewTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user1_password = 'TestPasswordView1!'
        cls.user1_data_for_create = { # Data for creating user1 via registration
            'email': 'viewuser1@example.com',
            'username': 'viewuser1_un', # Optional for registration, but good for direct creation
            'password': cls.user1_password,
            'password_confirm': cls.user1_password,
            'full_name': 'View User One',
            'first_name': 'View',
            'last_name': 'UserOne',
            'industry': 'Technology'
        }
        # User1 is created via registration test or directly if needed for other tests
        # cls.user1 = User.objects.create_user(
        #     email='viewuser1_direct@example.com', username='viewuser1_direct_un',
        #     password=cls.user1_password, full_name='View User One Direct'
        # )
        # cls.user1.profile.bio = "User1 initial bio." # Profile created by signal
        # cls.user1.profile.save()


        cls.user2_password = 'TestPasswordView2!'
        cls.user2 = User.objects.create_user(
            email='viewuser2@example.com', username='viewuser2_un',
            password=cls.user2_password, full_name='View User Two'
        )
        cls.user2.profile.bio = "User2's bio for testing."
        cls.user2.profile.save()

        cls.admin_password = 'AdminPasswordView1!'
        cls.admin_user = User.objects.create_superuser(
            email='viewadmin@example.com', username='viewadmin_un',
            password=cls.admin_password, full_name='View Admin User'
        )


    def get_jwt_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {'refresh': str(refresh), 'access': str(refresh.access_token)}

    def authenticate_client_with_jwt(self, user):
        tokens = self.get_jwt_tokens_for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')

    def setUp(self):
        super().setUp() # Call parent setUp if it exists
        # self.client is available from APITestCase


class UserRegistrationViewTests(UsersViewTestDataMixin, APITestCase):
    def test_user_registration_success(self):
        url = reverse('users:user-register')
        data = {
            'email': 'newregister@example.com',
            'username': 'newregister_un',
            'password': 'NewPassword123!',
            'password_confirm': 'NewPassword123!',
            'full_name': 'New Registered User',
            'industry': 'Education'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['email'], data['email'])
        self.assertEqual(response.data['username'], data['username'])
        self.assertIn('profile', response.data) # UserSerializer should return profile
        self.assertTrue(User.objects.filter(email=data['email']).exists())
        self.assertTrue(UserProfile.objects.filter(user__email=data['email']).exists())

    def test_user_registration_password_mismatch(self):
        url = reverse('users:user-register')
        data = {'email': 'mismatchreg@example.com', 'password': 'one', 'password_confirm': 'two'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirm', response.data)

    def test_user_registration_email_exists(self):
        # Create user1 first
        User.objects.create_user(**self.user1_data_for_create)
        url = reverse('users:user-register')
        data_duplicate_email = {
            'email': self.user1_data_for_create['email'], # Duplicate email
            'password': 'NewPassword123!',
            'password_confirm': 'NewPassword123!',
        }
        response = self.client.post(url, data_duplicate_email, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)


class UserLoginViewTests(UsersViewTestDataMixin, APITestCase):
    def test_user_login_success(self):
        # Create user1 first for login
        user_to_login = User.objects.create_user(
            email=self.user1_data_for_create['email'],
            username=self.user1_data_for_create['username'], # Provide username for create_user
            password=self.user1_data_for_create['password']
        )
        url = reverse('users:token_obtain_pair') # Standard DRF Simple JWT login URL
        data = {
            'email': self.user1_data_for_create['email'],
            'password': self.user1_data_for_create['password']
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        # If using a custom MyTokenObtainPairSerializer that adds user data:
        # self.assertIn('user', response.data)
        # self.assertEqual(response.data['user']['email'], self.user1_data_for_create['email'])

    def test_user_login_invalid_credentials(self):
        url = reverse('users:token_obtain_pair')
        data = {'email': self.user1_data_for_create['email'], 'password': 'wrongpassword'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED) # Standard for bad creds

    def test_token_refresh_success(self):
        # Login first to get a refresh token
        user_to_login = User.objects.create_user(email='refresh@example.com', password='password123', username='refresher')
        login_url = reverse('users:token_obtain_pair')
        login_data = {'email': 'refresh@example.com', 'password': 'password123'}
        login_response = self.client.post(login_url, login_data, format='json')
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        refresh_token = login_response.data['refresh']

        refresh_url = reverse('users:token_refresh')
        refresh_data = {'refresh': refresh_token}
        response = self.client.post(refresh_url, refresh_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertNotIn('refresh', response.data) # Standard refresh view doesn't return a new refresh token


class UserProfileViewTests(UsersViewTestDataMixin, APITestCase):
    def test_retrieve_own_profile_success(self):
        self.authenticate_client_with_jwt(self.user2) # user2 was created in setUpTestData
        url = reverse('users:user-profile-detail')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['email'], self.user2.email)
        self.assertIn('profile', response.data)
        self.assertEqual(response.data['profile']['bio'], self.user2.profile.bio)

    def test_retrieve_profile_unauthenticated_forbidden(self):
        url = reverse('users:user-profile-detail')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_own_profile_success(self):
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('users:user-profile-detail')
        data_to_update = {
            'full_name': 'View User Two (Updated)',
            'profession': 'Senior Developer',
            'profile_picture_url': 'http://example.com/updated_pic.png',
            'profile': {
                'bio': "User2's updated bio for view test.",
                'linkedin_url': 'https://linkedin.com/in/viewuser2updated'
            }
        }
        response = self.client.patch(url, data_to_update, format='json') # Use PATCH for partial update
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        
        self.user2.refresh_from_db()
        self.user2.profile.refresh_from_db()

        self.assertEqual(self.user2.full_name, data_to_update['full_name'])
        self.assertEqual(self.user2.profession, data_to_update['profession'])
        self.assertEqual(self.user2.profile_picture_url, data_to_update['profile_picture_url'])
        self.assertEqual(self.user2.profile.bio, data_to_update['profile']['bio'])
        self.assertEqual(self.user2.profile.linkedin_url, data_to_update['profile']['linkedin_url'])

    def test_update_profile_read_only_fields_not_changed(self):
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('users:user-profile-detail')
        original_email = self.user2.email
        original_username = self.user2.username
        data_attempt_readonly_change = {
            'email': 'cannotchange@example.com', # email is USERNAME_FIELD, typically not changed easily
            'username': 'cannotchange_un',        # username also typically not changed
            'uplas_xp_points': 10000             # Read-only
        }
        response = self.client.patch(url, data_attempt_readonly_change, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK) # Request is fine, but fields ignored

        self.user2.refresh_from_db()
        self.assertEqual(self.user2.email, original_email)
        self.assertEqual(self.user2.username, original_username)
        self.assertNotEqual(self.user2.uplas_xp_points, 10000)


class PasswordChangeViewTests(UsersViewTestDataMixin, APITestCase):
    def test_password_change_success(self):
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('users:change-password')
        data = {
            'old_password': self.user2_password,
            'new_password': 'NewSecurePassword321!',
            'new_password_confirm': 'NewSecurePassword321!'
        }
        response = self.client.put(url, data, format='json') # PUT or PATCH
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('Password updated successfully', response.data['detail'])
        
        self.user2.refresh_from_db()
        self.assertTrue(self.user2.check_password('NewSecurePassword321!'))

    def test_password_change_old_password_incorrect(self):
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('users:change-password')
        data = {'old_password': 'wrongoldpassword', 'new_password': 'new', 'new_password_confirm': 'new'}
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('old_password', response.data)

    def test_password_change_new_passwords_mismatch(self):
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('users:change-password')
        data = {'old_password': self.user2_password, 'new_password': 'new1', 'new_password_confirm': 'new2'}
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password_confirm', response.data)


class WhatsAppVerificationViewTests(UsersViewTestDataMixin, APITestCase):
    # Mock the actual sending of WhatsApp message
    @patch('apps.users.views.print') # Mock the print statement used as placeholder for sending
    def test_send_whatsapp_verification_code_success(self, mock_print_send):
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('users:whatsapp-send-code')
        whatsapp_number = '+12345678910'
        data = {'whatsapp_number': whatsapp_number}
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('Verification code sent', response.data['detail'])
        self.assertEqual(response.data['whatsapp_number'], whatsapp_number)

        self.user2.refresh_from_db()
        self.assertEqual(self.user2.whatsapp_number, whatsapp_number)
        self.assertIsNotNone(self.user2.whatsapp_verification_code)
        self.assertEqual(len(self.user2.whatsapp_verification_code), 6)
        mock_print_send.assert_called_once() # Check that our placeholder was called

    def test_send_whatsapp_code_number_already_verified_by_other(self):
        # user1 has a verified number
        self.user1.whatsapp_number = '+19876543210'
        self.user1.is_whatsapp_verified = True
        self.user1.save()

        self.authenticate_client_with_jwt(self.user2) # user2 trying to use user1's number
        url = reverse('users:whatsapp-send-code')
        data = {'whatsapp_number': '+19876543210'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already verified by another account", response.data['error'])

    def test_verify_whatsapp_code_success(self):
        self.authenticate_client_with_jwt(self.user2)
        # Set up user2 with a code
        self.user2.whatsapp_number = '+1112223333'
        generated_code = self.user2.generate_whatsapp_code() # Model method generates and saves

        url = reverse('users:whatsapp-verify-code')
        data = {'whatsapp_verification_code': generated_code}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('WhatsApp number verified successfully', response.data['detail'])

        self.user2.refresh_from_db()
        self.assertTrue(self.user2.is_whatsapp_verified)
        self.assertIsNone(self.user2.whatsapp_verification_code) # Code should be cleared

    def test_verify_whatsapp_code_invalid_code(self):
        self.authenticate_client_with_jwt(self.user2)
        self.user2.whatsapp_number = '+1112223333'
        self.user2.generate_whatsapp_code() # Generates a code
        
        url = reverse('users:whatsapp-verify-code')
        data = {'whatsapp_verification_code': '000000'} # Incorrect code
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Invalid verification code', str(response.data))

    def test_verify_whatsapp_code_expired(self):
        self.authenticate_client_with_jwt(self.user2)
        self.user2.whatsapp_number = '+1112223333'
        generated_code = self.user2.generate_whatsapp_code()
        # Manually set the code creation time to be in the past beyond expiry
        self.user2.whatsapp_code_created_at = timezone.now() - timezone.timedelta(minutes=settings.WHATSAPP_CODE_EXPIRY_MINUTES + 5)
        self.user2.save()

        url = reverse('users:whatsapp-verify-code')
        data = {'whatsapp_verification_code': generated_code}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Verification code has expired', str(response.data))


# TODO:
# - If AdminUserViewSet is implemented, add tests for its CRUD operations and permissions.
# - Test any specific error responses or edge cases for each view.
# - Test that non-owners cannot update profiles of others (should be covered by IsAccountOwnerOrReadOnly).
