from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.db.utils import IntegrityError # For testing unique constraints

from ..models import UserProfile, INDUSTRY_CHOICES, LANGUAGE_CHOICES, CURRENCY_CHOICES

User = get_user_model()

class UserModelTests(TestCase):

    def test_create_user_successful(self):
        """Test creating a new user is successful with an email and password."""
        email = "testuser@example.com"
        password = "testpassword123"
        user = User.objects.create_user(email=email, password=password)

        self.assertEqual(user.email, email)
        self.assertTrue(user.check_password(password))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active) # Default is_active should be True
        self.assertIsNotNone(user.username) # Username should be auto-generated
        self.assertTrue(user.username.startswith(email.split('@')[0]))

    def test_create_user_email_is_username_field(self):
        """Test that the USERNAME_FIELD is set to 'email'."""
        self.assertEqual(User.USERNAME_FIELD, 'email')

    def test_create_user_without_email_fails(self):
        """Test creating a user without an email raises an error."""
        with self.assertRaises(TypeError): # Or ValueError depending on AbstractUser implementation details
            User.objects.create_user(email=None, password="testpassword123")
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="testpassword123", username="user")


    def test_create_superuser_successful(self):
        """Test creating a superuser is successful."""
        email = "super@example.com"
        password = "superpassword123"
        admin_user = User.objects.create_superuser(email=email, password=password)

        self.assertEqual(admin_user.email, email)
        self.assertTrue(admin_user.check_password(password))
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.is_active)
        self.assertIsNotNone(admin_user.username)

    def test_user_str_representation(self):
        """Test the string representation of the user model."""
        email = "teststr@example.com"
        user = User.objects.create_user(email=email, password="password")
        self.assertEqual(str(user), email)

    def test_user_full_name_auto_population(self):
        """Test full_name is auto-populated from first_name and last_name."""
        user = User(email="testfullname@example.com", first_name="Test", last_name="User")
        user.save() # Trigger save method
        self.assertEqual(user.full_name, "Test User")

        user2 = User(email="testfirstname@example.com", first_name="OnlyFirst")
        user2.save()
        self.assertEqual(user2.full_name, "OnlyFirst")

    def test_user_default_values(self):
        """Test default values for user fields."""
        user = User.objects.create_user(email="defaults@example.com", password="password")
        self.assertEqual(user.preferred_language, 'en')
        self.assertEqual(user.preferred_currency, 'USD')
        self.assertEqual(user.uplas_xp_points, 0)
        self.assertFalse(user.is_premium_subscriber)
        self.assertIsNone(user.subscription_plan_name)
        self.assertIsNone(user.subscription_end_date)
        self.assertFalse(user.is_whatsapp_verified)

    def test_unique_email_constraint(self):
        """Test that email addresses must be unique."""
        email = "unique@example.com"
        User.objects.create_user(email=email, password="password1")
        with self.assertRaises(IntegrityError): # Django raises IntegrityError for unique constraint violations
            User.objects.create_user(email=email, password="password2", username="anotheruser")

    def test_unique_whatsapp_number_constraint(self):
        """Test that WhatsApp numbers must be unique if provided."""
        whatsapp_no = "+1234567890"
        User.objects.create_user(email="wa1@example.com", password="password", whatsapp_number=whatsapp_no)
        with self.assertRaises(IntegrityError):
            User.objects.create_user(email="wa2@example.com", password="password", whatsapp_number=whatsapp_no)
        # Test that null/blank whatsapp_number doesn't cause issues with uniqueness for other users
        User.objects.create_user(email="wa3@example.com", password="password", whatsapp_number=None)
        User.objects.create_user(email="wa4@example.com", password="password", whatsapp_number="") # Assuming blank is allowed
        self.assertTrue(True) # If it reaches here, null/blank didn't clash

    def test_generate_whatsapp_code(self):
        """Test the WhatsApp code generation method."""
        user = User.objects.create_user(email="whatsapptest@example.com", password="password")
        self.assertIsNone(user.whatsapp_verification_code)
        self.assertIsNone(user.whatsapp_code_created_at)

        code = user.generate_whatsapp_code()
        user.refresh_from_db() # Ensure we get the saved values

        self.assertIsNotNone(code)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        self.assertEqual(user.whatsapp_verification_code, code)
        self.assertIsNotNone(user.whatsapp_code_created_at)
        # Check if the timestamp is recent (within a small delta)
        self.assertTrue(timezone.now() - user.whatsapp_code_created_at < timedelta(seconds=5))


class UserProfileModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="profiletest@example.com", password="password")

    def test_user_profile_created_on_user_create(self):
        """Test that a UserProfile is automatically created when a User is created."""
        self.assertTrue(hasattr(self.user, 'profile'))
        self.assertIsInstance(self.user.profile, UserProfile)
        self.assertEqual(UserProfile.objects.count(), 1)
        self.assertEqual(self.user.profile.user, self.user)

    def test_user_profile_str_representation(self):
        """Test the string representation of the UserProfile model."""
        self.assertEqual(str(self.user.profile), f"{self.user.email}'s Profile")

    def test_user_profile_default_values(self):
        """Test default values for UserProfile fields."""
        profile = self.user.profile
        self.assertEqual(profile.bio, None) # Or "" if you change blank=True to default=""
        self.assertEqual(profile.linkedin_url, None)
        self.assertEqual(profile.preferred_tutor_persona, None)
        self.assertEqual(profile.learning_style_preference, {}) # Default is dict
        self.assertEqual(profile.areas_of_interest, [])     # Default is list
        self.assertEqual(profile.current_knowledge_level, {}) # Default is dict

    def test_user_profile_can_be_updated(self):
        """Test that UserProfile fields can be updated."""
        profile = self.user.profile
        profile.bio = "A test bio."
        profile.preferred_tutor_persona = "Socratic"
        profile.areas_of_interest = ["NLP", "Ethics"]
        profile.save()

        updated_profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(updated_profile.bio, "A test bio.")
        self.assertEqual(updated_profile.preferred_tutor_persona, "Socratic")
        self.assertEqual(updated_profile.areas_of_interest, ["NLP", "Ethics"])

    def test_user_deletion_cascades_to_profile(self):
        """Test that deleting a User also deletes their UserProfile."""
        user_id = self.user.id
        self.assertTrue(UserProfile.objects.filter(user_id=user_id).exists())
        self.user.delete()
        self.assertFalse(UserProfile.objects.filter(user_id=user_id).exists())
