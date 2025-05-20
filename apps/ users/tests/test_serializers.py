from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password # For context in assertions
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory


from ..serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserSerializer,
    UserProfileSerializer,
    WhatsAppVerificationSerializer
)
from ..models import UserProfile, INDUSTRY_CHOICES # Import choices for validation

User = get_user_model()

class UserRegistrationSerializerTests(TestCase):

    def setUp(self):
        self.valid_data = {
            "email": "testregister@example.com",
            "full_name": "Test User Register",
            "password": "ComplexPassword123!",
            "password_confirm": "ComplexPassword123!",
            "profession": "Developer",
            "industry": INDUSTRY_CHOICES[0][0], # Use a valid choice
        }
        # Create a dummy request object for context if serializer needs it (not strictly for UserRegistrationSerializer)
        factory = APIRequestFactory()
        self.request = factory.get('/') # or post('/')
        self.request.user = None # Simulate unauthenticated user for registration

    def test_registration_serializer_valid_data(self):
        """Test UserRegistrationSerializer with valid data creates a user."""
        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertIsInstance(user, User)
        self.assertEqual(user.email, self.valid_data["email"])
        self.assertEqual(user.full_name, self.valid_data["full_name"])
        self.assertTrue(user.check_password(self.valid_data["password"]))
        self.assertIsNotNone(user.username) # Check username is auto-generated
        self.assertTrue(UserProfile.objects.filter(user=user).exists()) # Check profile created

    def test_registration_serializer_password_mismatch(self):
        """Test passwords must match."""
        data = self.valid_data.copy()
        data["password_confirm"] = "WrongPassword123!"
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("password_confirm", serializer.errors)
        self.assertEqual(str(serializer.errors["password_confirm"][0]), "Password fields didn't match.")

    def test_registration_serializer_email_already_exists(self):
        """Test registration fails if email already exists."""
        User.objects.create_user(email=self.valid_data["email"], password="somepassword")
        serializer = UserRegistrationSerializer(data=self.valid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)
        self.assertEqual(str(serializer.errors["email"][0]), "A user with this email already exists.")

    def test_registration_serializer_missing_required_fields(self):
        """Test registration fails if required fields are missing."""
        required_fields = ["email", "full_name", "password", "password_confirm", "profession", "industry"]
        for field in required_fields:
            data = self.valid_data.copy()
            del data[field]
            serializer = UserRegistrationSerializer(data=data)
            self.assertFalse(serializer.is_valid(), f"Serializer should be invalid if {field} is missing.")
            self.assertIn(field, serializer.errors, f"{field} missing error not found.")

    def test_registration_serializer_industry_other_requires_details(self):
        """Test 'Other' industry requires other_industry_details."""
        data = self.valid_data.copy()
        data["industry"] = "Other"
        data.pop("other_industry_details", None) # Ensure it's not there
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("other_industry_details", serializer.errors)

        data["other_industry_details"] = "My Custom Industry"
        serializer = UserRegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_registration_serializer_clears_other_industry_details(self):
        """Test other_industry_details is cleared if industry is not 'Other'."""
        data = self.valid_data.copy()
        data["industry"] = INDUSTRY_CHOICES[0][0] # Not 'Other'
        data["other_industry_details"] = "Should be cleared"
        serializer = UserRegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        validated_data = serializer.validated_data
        self.assertIsNone(validated_data.get("other_industry_details"))


class UserLoginSerializerTests(TestCase):

    def setUp(self):
        self.email = "logintest@example.com"
        self.password = "loginPass123!"
        self.user = User.objects.create_user(email=self.email, password=self.password, username="logintestuser")
        
        # Create a dummy request object for context
        factory = APIRequestFactory()
        self.request = factory.post('/api/users/login/') # Simulate a post request
        self.request.user = None # Unauthenticated for login attempt

    def test_login_serializer_valid_credentials(self):
        """Test UserLoginSerializer with valid credentials."""
        data = {"email": self.email, "password": self.password}
        serializer = UserLoginSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["user"], self.user)

    def test_login_serializer_invalid_password(self):
        """Test UserLoginSerializer with invalid password."""
        data = {"email": self.email, "password": "wrongpassword"}
        serializer = UserLoginSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors) # Default error key for authenticate issues
        self.assertEqual(str(serializer.errors["non_field_errors"][0]), "Unable to log in with provided credentials.")

    def test_login_serializer_non_existent_email(self):
        """Test UserLoginSerializer with a non-existent email."""
        data = {"email": "nosuchuser@example.com", "password": self.password}
        serializer = UserLoginSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_login_serializer_inactive_user(self):
        """Test UserLoginSerializer with an inactive user."""
        self.user.is_active = False
        self.user.save()
        data = {"email": self.email, "password": self.password}
        serializer = UserLoginSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)
        self.assertEqual(str(serializer.errors["non_field_errors"][0]), "User account is disabled.")

    def test_login_serializer_missing_fields(self):
        """Test UserLoginSerializer with missing email or password."""
        data_no_email = {"password": self.password}
        serializer_no_email = UserLoginSerializer(data=data_no_email, context={'request': self.request})
        self.assertFalse(serializer_no_email.is_valid())
        self.assertIn("email", serializer_no_email.errors)

        data_no_password = {"email": self.email}
        serializer_no_password = UserLoginSerializer(data=data_no_password, context={'request': self.request})
        self.assertFalse(serializer_no_password.is_valid())
        self.assertIn("password", serializer_no_password.errors)


class UserSerializerTests(TestCase):

    def setUp(self):
        self.user_data = {
            "email": "profileserializertest@example.com",
            "password": "password123",
            "full_name": "Profile Test User",
            "industry": INDUSTRY_CHOICES[1][0],
            "profession": "Tester"
        }
        self.user = User.objects.create_user(**self.user_data)
        # UserProfile is created by signal
        self.profile_data = {
            "bio": "Test bio for profile.",
            "linkedin_url": "https://linkedin.com/in/testuser",
            "preferred_tutor_persona": "Friendly"
        }
        UserProfile.objects.filter(user=self.user).update(**self.profile_data)
        self.user.refresh_from_db() # Refresh to get profile relation updated
        
        factory = APIRequestFactory()
        self.request = factory.get('/') # Dummy request for context
        self.request.user = self.user # Simulate authenticated user for profile view/update

    def test_user_serializer_output_data(self):
        """Test UserSerializer correctly serializes user and profile data."""
        serializer = UserSerializer(self.user, context={'request': self.request})
        data = serializer.data

        self.assertEqual(data["email"], self.user.email)
        self.assertEqual(data["full_name"], self.user.full_name)
        self.assertEqual(data["industry"], self.user.industry)
        self.assertIsNotNone(data["profile"])
        self.assertEqual(data["profile"]["bio"], self.profile_data["bio"])
        self.assertEqual(data["profile"]["linkedin_url"], self.profile_data["linkedin_url"])
        self.assertEqual(data["profile"]["preferred_tutor_persona"], self.profile_data["preferred_tutor_persona"])
        self.assertNotIn("password", data) # Password should not be serialized

    def test_user_serializer_update_user_and_profile(self):
        """Test UserSerializer can update both User and nested UserProfile fields."""
        update_data = {
            "full_name": "Updated Full Name",
            "profession": "Senior Tester",
            "profile": {
                "bio": "Updated bio.",
                "github_url": "https://github.com/testuser"
            }
        }
        serializer = UserSerializer(self.user, data=update_data, partial=True, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_user = serializer.save()

        self.assertEqual(updated_user.full_name, update_data["full_name"])
        self.assertEqual(updated_user.profession, update_data["profession"])
        self.assertIsNotNone(updated_user.profile)
        self.assertEqual(updated_user.profile.bio, update_data["profile"]["bio"])
        self.assertEqual(updated_user.profile.github_url, update_data["profile"]["github_url"])
        # Check that an original profile field not in update_data is retained
        self.assertEqual(updated_user.profile.linkedin_url, self.profile_data["linkedin_url"])

    def test_user_serializer_update_only_user_fields(self):
        """Test UserSerializer updates only User fields when profile is not in data."""
        update_data = {"city": "Nairobi"}
        serializer = UserSerializer(self.user, data=update_data, partial=True, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_user = serializer.save()
        self.assertEqual(updated_user.city, "Nairobi")
        # Ensure profile bio is unchanged
        self.assertEqual(updated_user.profile.bio, self.profile_data["bio"])

    def test_user_serializer_update_only_profile_fields(self):
        """Test UserSerializer updates only UserProfile fields."""
        update_data = {"profile": {"learning_goals": "Master Django Testing"}}
        serializer = UserSerializer(self.user, data=update_data, partial=True, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_user = serializer.save()
        self.assertEqual(updated_user.profile.learning_goals, "Master Django Testing")
        # Ensure user full_name is unchanged
        self.assertEqual(updated_user.full_name, self.user_data["full_name"])

    def test_user_serializer_update_first_last_name_populates_full_name(self):
        """Test updating first_name/last_name also updates full_name."""
        update_data = {
            "first_name": "NewFirst",
            "last_name": "NewLast"
        }
        # Clear existing full_name to ensure it's re-calculated by serializer/model
        self.user.full_name = "" 
        self.user.save()

        serializer = UserSerializer(self.user, data=update_data, partial=True, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_user = serializer.save()
        self.assertEqual(updated_user.first_name, "NewFirst")
        self.assertEqual(updated_user.last_name, "NewLast")
        self.assertEqual(updated_user.full_name, "NewFirst NewLast")


class UserProfileSerializerDirectTests(TestCase): # Less common to use directly, but good for completeness
    def setUp(self):
        self.user = User.objects.create_user(email="profileonly@example.com", password="password")
        self.profile = self.user.profile # Profile created by signal

    def test_profile_serializer_can_update_fields(self):
        data = {
            "bio": "Directly updated bio.",
            "learning_style_preference": {"visual": 0.8}
        }
        serializer = UserProfileSerializer(self.profile, data=data, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bio, "Directly updated bio.")
        self.assertEqual(self.profile.learning_style_preference, {"visual": 0.8})


class WhatsAppVerificationSerializerTests(TestCase):

    def test_whatsapp_verification_serializer_valid_code(self):
        """Test WhatsAppVerificationSerializer with a valid code."""
        data = {"code": "123456"}
        serializer = WhatsAppVerificationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["code"], "123456")

    def test_whatsapp_verification_serializer_invalid_code_non_numeric(self):
        """Test code must be numeric."""
        data = {"code": "abcdef"}
        serializer = WhatsAppVerificationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("code", serializer.errors)
        self.assertEqual(str(serializer.errors["code"][0]), "Verification code must be numeric.")

    def test_whatsapp_verification_serializer_invalid_code_too_short(self):
        """Test code must be 6 digits."""
        data = {"code": "123"}
        serializer = WhatsAppVerificationSerializer(data=data)
        self.assertFalse(serializer.is_valid()) # Relies on CharField min_length
        self.assertIn("code", serializer.errors)
        # Default Django CharField error for min_length
        self.assertTrue("Ensure this field has at least 6 characters." in str(serializer.errors["code"][0]))


    def test_whatsapp_verification_serializer_invalid_code_too_long(self):
        """Test code must be 6 digits."""
        data = {"code": "1234567"}
        serializer = WhatsAppVerificationSerializer(data=data)
        self.assertFalse(serializer.is_valid()) # Relies on CharField max_length
        self.assertIn("code", serializer.errors)
        # Default Django CharField error for max_length
        self.assertTrue("Ensure this field has no more than 6 characters." in str(serializer.errors["code"][0]))


    def test_whatsapp_verification_serializer_missing_code(self):
        """Test code is required."""
        data = {}
        serializer = WhatsAppVerificationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("code", serializer.errors)
        self.assertEqual(str(serializer.errors["code"][0]), "This field is required.")
