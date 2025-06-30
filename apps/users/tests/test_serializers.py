from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from uuid import UUID

from rest_framework.test import APIRequestFactory # For providing request context
from rest_framework.exceptions import ValidationError

# Import your custom User model, UserProfile model, and serializers
from apps.users.models import UserProfile
from apps.users.serializers import (
    UserProfileSerializer,
    UserSerializer,
    UserRegistrationSerializer,
    UserLoginSerializer, # If you created a custom one, otherwise test via views
    PasswordChangeSerializer,
    SendWhatsAppVerificationSerializer,
    VerifyWhatsAppSerializer
)

User = get_user_model()

# Test Data Setup Mixin (adapted for serializer tests)
class UsersSerializerTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user1_data = {
            'email': 'serializeruser1@example.com',
            'password': 'TestPasswordSer1!',
            'username': 'serializeruser1_un',
            'full_name': 'Serializer User One',
            'first_name': 'Serializer',
            'last_name': 'UserOne',
            'industry': 'Technology'
        }
        cls.user1 = User.objects.create_user(**cls.user1_data)
        # Profile is created by signal

        cls.user2_data = {
            'email': 'serializeruser2@example.com',
            'password': 'TestPasswordSer2!',
            'username': 'serializeruser2_un',
            'full_name': 'Serializer User Two',
        }
        cls.user2 = User.objects.create_user(**cls.user2_data)

        # For providing request context to serializers
        cls.factory = APIRequestFactory()
        cls.request_user1 = cls.factory.get('/fake-users-endpoint')
        cls.request_user1.user = cls.user1
        cls.request_user1.method = 'GET' # Can be changed in tests

        cls.request_user2 = cls.factory.get('/fake-users-endpoint')
        cls.request_user2.user = cls.user2
        cls.request_user2.method = 'GET'


class UserProfileSerializerTests(UsersSerializerTestDataMixin, TestCase):
    def test_serialization_output(self):
        profile = self.user1.profile
        serializer = UserProfileSerializer(instance=profile)
        data = serializer.data

        self.assertEqual(data['id'], str(profile.id))
        self.assertEqual(data['user'], self.user1.pk) # Default shows PK for OneToOne
        self.assertEqual(data['bio'], profile.bio) # Initially None/blank
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)

    def test_deserialization_update_valid(self):
        profile = self.user1.profile
        data = {
            "bio": "Updated bio for serializer test.",
            "linkedin_url": "https://linkedin.com/in/serializeruser1",
            "preferred_tutor_persona": "Friendly",
            "learning_goals": "Master DRF serializers."
        }
        serializer = UserProfileSerializer(instance=profile, data=data, partial=True, context={'request': self.request_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_profile = serializer.save()

        self.assertEqual(updated_profile.bio, data['bio'])
        self.assertEqual(updated_profile.linkedin_url, data['linkedin_url'])
        self.assertEqual(updated_profile.preferred_tutor_persona, data['preferred_tutor_persona'])

    def test_user_field_is_read_only(self):
        profile = self.user1.profile
        data = {"user": self.user2.pk, "bio": "Attempting to change user."} # user is read_only
        serializer = UserProfileSerializer(instance=profile, data=data, partial=True)
        self.assertTrue(serializer.is_valid()) # Valid because read_only field is ignored on input
        updated_profile = serializer.save()
        self.assertEqual(updated_profile.user, self.user1) # User should not have changed


class UserSerializerTests(UsersSerializerTestDataMixin, TestCase):
    def test_serialization_output_with_profile(self):
        # Ensure profile has some data for a more complete test
        self.user1.profile.bio = "User1 bio for UserSerializer test."
        self.user1.profile.github_url = "https://github.com/serializeruser1"
        self.user1.profile.save()

        serializer = UserSerializer(instance=self.user1)
        data = serializer.data

        self.assertEqual(data['email'], self.user1.email)
        self.assertEqual(data['username'], self.user1.username)
        self.assertEqual(data['full_name'], self.user1.full_name)
        self.assertEqual(data['industry'], self.user1.industry)
        self.assertEqual(data['industry_display'], dict(INDUSTRY_CHOICES).get(self.user1.industry))
        self.assertIn('profile', data)
        self.assertEqual(data['profile']['bio'], "User1 bio for UserSerializer test.")
        self.assertEqual(data['profile']['github_url'], "https://github.com/serializeruser1")
        self.assertNotIn('password', data) # Password should be write_only or not included

    def test_deserialization_update_user_and_profile(self):
        data = {
            "full_name": "Serializer User One (Updated)",
            "profession": "Lead Developer",
            "profile_picture_url": "http://example.com/new_pic.jpg",
            "profile": {
                "bio": "My updated bio via UserSerializer.",
                "website_url": "https://myupdated.site"
            }
        }
        serializer = UserSerializer(instance=self.user1, data=data, partial=True, context={'request': self.request_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_user = serializer.save()
        updated_user.profile.refresh_from_db() # Ensure profile changes are reloaded

        self.assertEqual(updated_user.full_name, data['full_name'])
        self.assertEqual(updated_user.profession, data['profession'])
        self.assertEqual(updated_user.profile.bio, data['profile']['bio'])
        self.assertEqual(updated_user.profile.website_url, data['profile']['website_url'])

    def test_validate_industry_other_requires_details(self):
        data = {"industry": "Other"} # Missing other_industry_details
        serializer = UserSerializer(instance=self.user1, data=data, partial=True, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('industry', serializer.errors) # Or non_field_errors based on actual implementation
        self.assertIn("Please specify details if 'Other' industry is selected.", str(serializer.errors['industry']))

        data_with_details = {"industry": "Other", "other_industry_details": "Specialized Tech Field"}
        serializer_ok = UserSerializer(instance=self.user1, data=data_with_details, partial=True, context={'request': self.request_user1})
        self.assertTrue(serializer_ok.is_valid(), serializer_ok.errors)

    def test_validate_whatsapp_number_format(self):
        data = {"whatsapp_number": "1234567890"} # Missing '+'
        serializer = UserSerializer(instance=self.user1, data=data, partial=True, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('whatsapp_number', serializer.errors)
        self.assertIn("must start with a country code", str(serializer.errors['whatsapp_number']))

        data_ok = {"whatsapp_number": "+11234567890"}
        serializer_ok = UserSerializer(instance=self.user1, data=data_ok, partial=True, context={'request': self.request_user1})
        self.assertTrue(serializer_ok.is_valid(), serializer_ok.errors)


class UserRegistrationSerializerTests(UsersSerializerTestDataMixin, TestCase):
    def test_valid_registration(self):
        data = {
            "email": "newuser@example.com",
            "username": "newuser_reg_test", # Optional, can be auto-generated
            "password": "StrongPassword123!",
            "password_confirm": "StrongPassword123!",
            "full_name": "New Registered User",
            "industry": "Education"
        }
        serializer = UserRegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertEqual(user.email, data['email'])
        self.assertEqual(user.username, data['username'])
        self.assertTrue(user.check_password(data['password']))
        self.assertIsNotNone(user.profile) # Profile created by signal

    def test_registration_password_mismatch(self):
        data = {"email": "mismatch@example.com", "password": "one", "password_confirm": "two"}
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password_confirm', serializer.errors)
        self.assertIn("Password fields didn't match.", str(serializer.errors['password_confirm']))

    def test_registration_email_exists(self):
        data = {"email": self.user1.email, "password": "pw", "password_confirm": "pw"}
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)
        self.assertIn("already exists", str(serializer.errors['email']))

    def test_registration_username_exists(self):
        data = {"email": "unique@example.com", "username": self.user1.username, "password": "pw", "password_confirm": "pw"}
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('username', serializer.errors)
        self.assertIn("already taken", str(serializer.errors['username']))
    
    def test_registration_industry_other_requires_details(self):
        data = {
            "email": "industryother@example.com", "password": "pw", "password_confirm": "pw",
            "industry": "Other" # Missing other_industry_details
        }
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('other_industry_details', serializer.errors)
        self.assertIn("Please specify details if 'Other' industry is selected.", str(serializer.errors['other_industry_details']))


class PasswordChangeSerializerTests(UsersSerializerTestDataMixin, TestCase):
    def test_password_change_valid(self):
        data = {
            "old_password": self.user1_data['password'],
            "new_password": "NewStrongPassword456!",
            "new_password_confirm": "NewStrongPassword456!"
        }
        serializer = PasswordChangeSerializer(data=data, context={'request': self.request_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.user1.refresh_from_db()
        self.assertTrue(self.user1.check_password("NewStrongPassword456!"))

    def test_password_change_old_password_incorrect(self):
        data = {"old_password": "wrongoldpassword", "new_password": "new", "new_password_confirm": "new"}
        serializer = PasswordChangeSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('old_password', serializer.errors)

    def test_password_change_new_passwords_mismatch(self):
        data = {"old_password": self.user1_data['password'], "new_password": "new1", "new_password_confirm": "new2"}
        serializer = PasswordChangeSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('new_password_confirm', serializer.errors)


class WhatsAppVerificationSerializerTests(UsersSerializerTestDataMixin, TestCase):
    def test_send_whatsapp_verification_serializer_valid(self):
        data = {"whatsapp_number": "+12345678901"}
        serializer = SendWhatsAppVerificationSerializer(data=data, context={'request': self.request_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_send_whatsapp_verification_serializer_invalid_format(self):
        data = {"whatsapp_number": "12345678901"} # Missing '+'
        serializer = SendWhatsAppVerificationSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('whatsapp_number', serializer.errors)

    def test_verify_whatsapp_serializer_valid_code(self):
        self.user1.whatsapp_verification_code = "123456"
        self.user1.whatsapp_code_created_at = timezone.now()
        self.user1.save()

        data = {"whatsapp_verification_code": "123456"}
        serializer = VerifyWhatsAppSerializer(data=data, context={'request': self.request_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_verify_whatsapp_serializer_invalid_code(self):
        self.user1.whatsapp_verification_code = "123456"
        self.user1.whatsapp_code_created_at = timezone.now()
        self.user1.save()
        data = {"whatsapp_verification_code": "654321"}
        serializer = VerifyWhatsAppSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('whatsapp_verification_code', serializer.errors)
        self.assertIn("Invalid verification code.", str(serializer.errors['whatsapp_verification_code']))

    def test_verify_whatsapp_serializer_code_expired(self):
        self.user1.whatsapp_verification_code = "123456"
        # Set creation time to be older than expiry (default 10 mins in serializer)
        self.user1.whatsapp_code_created_at = timezone.now() - timezone.timedelta(minutes=settings.WHATSAPP_CODE_EXPIRY_MINUTES + 5)
        self.user1.save()
        data = {"whatsapp_verification_code": "123456"}
        serializer = VerifyWhatsAppSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('whatsapp_verification_code', serializer.errors)
        self.assertIn("Verification code has expired.", str(serializer.errors['whatsapp_verification_code']))

# Add tests for UserLoginSerializer if it's custom and not just DRF Simple JWT's default.
# If MyTokenObtainPairSerializer is used, test its validate method and token claims.
