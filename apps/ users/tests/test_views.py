from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch # For mocking external services like WhatsApp sending

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from ..models import UserProfile, INDUSTRY_CHOICES

User = get_user_model()

class UserAuthViewTests(APITestCase):

    def setUp(self):
        self.register_url = reverse('users:register')
        self.login_url = reverse('users:login')
        self.token_refresh_url = reverse('users:token_refresh')

        self.user_data = {
            "email": "test@example.com",
            "full_name": "Test User",
            "password": "ComplexPassword123!",
            "password_confirm": "ComplexPassword123!",
            "profession": "Developer",
            "industry": INDUSTRY_CHOICES[0][0],
        }
        self.login_credentials = {
            "email": self.user_data["email"],
            "password": self.user_data["password"]
        }

    def test_user_registration_success(self):
        """Ensure new user can be registered."""
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email=self.user_data["email"]).exists())
        user = User.objects.get(email=self.user_data["email"])
        self.assertEqual(user.full_name, self.user_data["full_name"])
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_user_registration_email_exists(self):
        """Ensure registration fails if email already exists."""
        User.objects.create_user(email=self.user_data["email"], password="anotherpassword")
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_user_registration_password_mismatch(self):
        """Ensure registration fails if passwords do not match."""
        data = self.user_data.copy()
        data["password_confirm"] = "WrongPassword!"
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_user_login_success(self):
        """Ensure registered user can log in and receive tokens."""
        self.client.post(self.register_url, self.user_data, format='json') # Register user first
        response = self.client.post(self.login_url, self.login_credentials, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["email"], self.user_data["email"])

    def test_user_login_invalid_credentials(self):
        """Ensure login fails with invalid credentials."""
        self.client.post(self.register_url, self.user_data, format='json')
        invalid_creds = {"email": self.user_data["email"], "password": "wrongpassword"}
        response = self.client.post(self.login_url, invalid_creds, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED) # Based on UserLoginSerializer raising ValidationError with code='authorization'

    def test_user_login_inactive_user(self):
        """Ensure login fails for an inactive user."""
        user = User.objects.create_user(**self.user_data) # Create user directly to modify
        user.is_active = False
        user.save()
        response = self.client.post(self.login_url, self.login_credentials, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_refresh_success(self):
        """Ensure JWT token can be refreshed."""
        self.client.post(self.register_url, self.user_data, format='json')
        login_response = self.client.post(self.login_url, self.login_credentials, format='json')
        refresh_token = login_response.data["refresh"]
        
        response = self.client.post(self.token_refresh_url, {"refresh": refresh_token}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotEqual(response.data["access"], login_response.data["access"]) # New access token

    def test_token_refresh_invalid_token(self):
        """Ensure token refresh fails with an invalid refresh token."""
        response = self.client.post(self.token_refresh_url, {"refresh": "invalidtoken"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserProfileViewTests(APITestCase):
    def setUp(self):
        self.profile_url = reverse('users:user-profile')
        self.user = User.objects.create_user(
            email="profileview@example.com",
            password="password123",
            full_name="Profile Viewer",
            industry=INDUSTRY_CHOICES[0][0]
        )
        # UserProfile created by signal
        self.user.profile.bio = "Initial bio"
        self.user.profile.save()

        self.client = APIClient() # Use APIClient for easy authentication

    def test_get_profile_authenticated(self):
        """Authenticated user can retrieve their profile."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.profile_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)
        self.assertEqual(response.data["profile"]["bio"], "Initial bio")

    def test_get_profile_unauthenticated(self):
        """Unauthenticated user cannot retrieve profile."""
        response = self.client.get(self.profile_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_profile_authenticated(self):
        """Authenticated user can update their profile."""
        self.client.force_authenticate(user=self.user)
        update_data = {
            "full_name": "Updated Name",
            "city": "Test City",
            "profile": {
                "bio": "Updated bio information.",
                "linkedin_url": "https://linkedin.com/in/updated"
            }
        }
        response = self.client.put(self.profile_url, update_data, format='json') # PUT for full update
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.full_name, "Updated Name")
        self.assertEqual(self.user.city, "Test City")
        self.assertEqual(self.user.profile.bio, "Updated bio information.")
        self.assertEqual(self.user.profile.linkedin_url, "https://linkedin.com/in/updated")

    def test_partial_update_profile_authenticated(self):
        """Authenticated user can partially update their profile."""
        self.client.force_authenticate(user=self.user)
        patch_data = {"profile": {"preferred_tutor_persona": "Socratic"}}
        response = self.client.patch(self.profile_url, patch_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.preferred_tutor_persona, "Socratic")
        self.assertEqual(self.user.profile.bio, "Initial bio") # Check other fields unchanged


class WhatsAppVerificationViewTests(APITestCase):
    def setUp(self):
        self.send_code_url = reverse('users:whatsapp-send-code')
        self.verify_code_url = reverse('users:whatsapp-verify-code')
        self.user_no_whatsapp = User.objects.create_user(email="wa_test1@example.com", password="password")
        self.user_with_whatsapp = User.objects.create_user(
            email="wa_test2@example.com",
            password="password",
            whatsapp_number="+12345678900"
        )
        self.client = APIClient()

    @patch('apps.users.views.print') # Mock the print statement simulating message sending
    def test_send_whatsapp_code_success(self, mock_print):
        """Test sending WhatsApp verification code successfully."""
        self.client.force_authenticate(user=self.user_with_whatsapp)
        response = self.client.post(self.send_code_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Verification code sent to your WhatsApp number.")
        self.user_with_whatsapp.refresh_from_db()
        self.assertIsNotNone(self.user_with_whatsapp.whatsapp_verification_code)
        self.assertIsNotNone(self.user_with_whatsapp.whatsapp_code_created_at)
        mock_print.assert_called_once() # Check that our mock "send" was called

    def test_send_whatsapp_code_no_number(self):
        """Test sending code fails if user has no WhatsApp number."""
        self.client.force_authenticate(user=self.user_no_whatsapp)
        response = self.client.post(self.send_code_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Please add your WhatsApp number in your profile first.")

    def test_send_whatsapp_code_already_verified(self):
        """Test sending code fails if number is already verified."""
        self.user_with_whatsapp.is_whatsapp_verified = True
        self.user_with_whatsapp.save()
        self.client.force_authenticate(user=self.user_with_whatsapp)
        response = self.client.post(self.send_code_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Your WhatsApp number is already verified.")

    def test_send_whatsapp_code_rate_limit(self):
        """Test rate limiting for sending code."""
        self.client.force_authenticate(user=self.user_with_whatsapp)
        self.user_with_whatsapp.generate_whatsapp_code() # First code sent
        # Attempt to send again immediately
        response = self.client.post(self.send_code_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_verify_whatsapp_code_success(self):
        """Test successful WhatsApp verification."""
        self.client.force_authenticate(user=self.user_with_whatsapp)
        code = self.user_with_whatsapp.generate_whatsapp_code()
        response = self.client.post(self.verify_code_url, {"code": code}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "WhatsApp number verified successfully.")
        self.user_with_whatsapp.refresh_from_db()
        self.assertTrue(self.user_with_whatsapp.is_whatsapp_verified)
        self.assertIsNone(self.user_with_whatsapp.whatsapp_verification_code)

    def test_verify_whatsapp_code_invalid_code(self):
        """Test verification fails with an invalid code."""
        self.client.force_authenticate(user=self.user_with_whatsapp)
        self.user_with_whatsapp.generate_whatsapp_code()
        response = self.client.post(self.verify_code_url, {"code": "000000"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Invalid verification code.")
        self.user_with_whatsapp.refresh_from_db()
        self.assertFalse(self.user_with_whatsapp.is_whatsapp_verified)

    def test_verify_whatsapp_code_expired(self):
        """Test verification fails if the code has expired."""
        self.client.force_authenticate(user=self.user_with_whatsapp)
        code = self.user_with_whatsapp.generate_whatsapp_code()
        # Manually expire the code
        self.user_with_whatsapp.whatsapp_code_created_at = timezone.now() - timedelta(minutes=15)
        self.user_with_whatsapp.save()
        response = self.client.post(self.verify_code_url, {"code": code}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Verification code has expired. Please request a new one.")
        self.user_with_whatsapp.refresh_from_db()
        self.assertFalse(self.user_with_whatsapp.is_whatsapp_verified)
        self.assertIsNone(self.user_with_whatsapp.whatsapp_verification_code) # Code should be cleared

    def test_verify_whatsapp_code_no_code_sent(self):
        """Test verification fails if no code was previously sent."""
        self.client.force_authenticate(user=self.user_with_whatsapp)
        # No code generated for self.user_with_whatsapp in this specific test path initially
        self.user_with_whatsapp.whatsapp_verification_code = None
        self.user_with_whatsapp.whatsapp_code_created_at = None
        self.user_with_whatsapp.save()
        response = self.client.post(self.verify_code_url, {"code": "123456"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "No verification code was found for your account. Please request one first.")

    def test_verify_whatsapp_code_already_verified(self):
        """Test verification attempt on an already verified number."""
        self.client.force_authenticate(user=self.user_with_whatsapp)
        self.user_with_whatsapp.is_whatsapp_verified = True
        self.user_with_whatsapp.save()
        response = self.client.post(self.verify_code_url, {"code": "123456"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "WhatsApp number already verified.")
