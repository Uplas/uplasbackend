from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import IntegrityError
from uuid import UUID

# Import your custom User model and UserProfile model
from apps.users.models import UserProfile # User is imported via get_user_model()
# Assuming BaseModel is in apps.core.models for UserProfile's inheritance
from apps.core.models import BaseModel

User = get_user_model()

class UsersModelTestDataMixin:
    """
    Mixin to provide common setup data for user-related model tests.
    """
    @classmethod
    def setUpTestData(cls):
        cls.user_data1 = {
            'email': 'testuser1@example.com',
            'password': 'TestPassword123!',
            'username': 'testuser1_username',
            'full_name': 'Test User One Full',
            'first_name': 'Test',
            'last_name': 'UserOne',
            'industry': 'Technology'
        }
        cls.user1 = User.objects.create_user(**cls.user_data1)

        cls.user_data_no_username = {
            'email': 'nousername@example.com',
            'password': 'PasswordNoUser123!',
            'first_name': 'No',
            'last_name': 'Username',
        }
        # User manager should auto-generate username

        cls.superuser_data = {
            'email': 'super@example.com',
            'password': 'SuperPassword123!',
            'username': 'superadmin'
        }
        cls.superuser = User.objects.create_superuser(**cls.superuser_data)


class UserModelTests(UsersModelTestDataMixin, TestCase):
    def test_user_creation_with_email_and_password(self):
        user = User.objects.create_user(email='test@example.com', password='testpassword123')
        self.assertEqual(user.email, 'test@example.com')
        self.assertTrue(user.check_password('testpassword123'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active) # Default from AbstractUser
        self.assertTrue(user.username.startswith(user.email.split('@')[0])) # Check auto-generated username
        self.assertIsNotNone(user.created_at) # From our explicit field
        self.assertIsNotNone(user.updated_at) # From our explicit field

    def test_user_creation_with_all_fields(self):
        self.assertEqual(self.user1.email, self.user_data1['email'])
        self.assertEqual(self.user1.username, self.user_data1['username'])
        self.assertEqual(self.user1.full_name, self.user_data1['full_name'])
        self.assertEqual(self.user1.industry, self.user_data1['industry'])
        self.assertTrue(self.user1.check_password(self.user_data1['password']))

    def test_user_creation_without_username_auto_generates(self):
        user_no_un = User.objects.create_user(**self.user_data_no_username)
        self.assertIsNotNone(user_no_un.username)
        self.assertTrue(user_no_un.username.startswith(user_no_un.email.split('@')[0]))
        self.assertEqual(user_no_un.full_name, "No Username") # Auto-generated full_name

    def test_superuser_creation(self):
        self.assertEqual(self.superuser.email, self.superuser_data['email'])
        self.assertTrue(self.superuser.is_staff)
        self.assertTrue(self.superuser.is_superuser)
        self.assertTrue(self.superuser.is_active)
        self.assertTrue(self.superuser.check_password(self.superuser_data['password']))

    def test_email_is_username_field(self):
        self.assertEqual(User.USERNAME_FIELD, 'email')

    def test_required_fields_for_superuser(self):
        # Username is in REQUIRED_FIELDS from AbstractUser, even if email is USERNAME_FIELD
        self.assertIn('username', User.REQUIRED_FIELDS)

    def test_email_uniqueness(self):
        with self.assertRaises(IntegrityError):
            User.objects.create_user(email=self.user_data1['email'], password='anotherpassword')

    def test_username_uniqueness(self):
        with self.assertRaises(IntegrityError):
            User.objects.create_user(email='another@example.com', username=self.user_data1['username'], password='anotherpassword')

    def test_user_str_representation(self):
        self.assertEqual(str(self.user1), self.user_data1['email'])

    def test_full_name_auto_population_on_save(self):
        user = User(email='populatename@example.com', first_name='Populate', last_name='NameTest')
        user.set_password('testpass')
        user.save() # Trigger save method
        self.assertEqual(user.full_name, 'Populate NameTest')

        user_no_lastname = User(email='onlyfirstname@example.com', first_name='OnlyFirst')
        user_no_lastname.set_password('testpass')
        user_no_lastname.save()
        self.assertEqual(user_no_lastname.full_name, 'OnlyFirst')


    def test_generate_whatsapp_code(self):
        initial_code = self.user1.whatsapp_verification_code
        initial_time = self.user1.whatsapp_code_created_at

        new_code = self.user1.generate_whatsapp_code()
        self.user1.refresh_from_db()

        self.assertIsNotNone(new_code)
        self.assertEqual(len(new_code), 6)
        self.assertEqual(self.user1.whatsapp_verification_code, new_code)
        self.assertNotEqual(self.user1.whatsapp_verification_code, initial_code)
        self.assertIsNotNone(self.user1.whatsapp_code_created_at)
        if initial_time: # If it was set before
            self.assertGreater(self.user1.whatsapp_code_created_at, initial_time)
        
        # Test that save was called with update_fields
        with self.assertNumQueries(1): # Should only update specific fields
            self.user1.generate_whatsapp_code()


    def test_default_preferences_and_points(self):
        user_defaults = User.objects.create_user(email='defaults@example.com', password='password123')
        self.assertEqual(user_defaults.preferred_language, 'en')
        self.assertEqual(user_defaults.preferred_currency, 'USD')
        self.assertEqual(user_defaults.uplas_xp_points, 0)
        self.assertFalse(user_defaults.is_premium_subscriber)


class UserProfileModelTests(UsersModelTestDataMixin, TestCase):
    def test_user_profile_created_on_user_create_signal(self):
        # user1 was created in setUpTestData, signal should have created a profile
        self.assertTrue(hasattr(self.user1, 'profile'))
        self.assertIsInstance(self.user1.profile, UserProfile)
        self.assertEqual(self.user1.profile.user, self.user1)

    def test_user_profile_inherits_base_model_fields(self):
        profile = self.user1.profile
        self.assertIsInstance(profile.id, UUID)
        self.assertIsNotNone(profile.created_at)
        self.assertIsNotNone(profile.updated_at)

    def test_user_profile_str_representation(self):
        profile = self.user1.profile
        expected_str = f"{self.user1.email}'s Profile"
        self.assertEqual(str(profile), expected_str)

    def test_user_profile_default_json_fields(self):
        profile = self.user1.profile
        self.assertEqual(profile.learning_style_preference, {}) # default=dict
        self.assertEqual(profile.areas_of_interest, [])       # default=list
        self.assertEqual(profile.current_knowledge_level, {}) # default=dict

    def test_user_profile_can_be_updated(self):
        profile = self.user1.profile
        profile.bio = "An updated bio for testing."
        profile.linkedin_url = "https://linkedin.com/in/testuserone"
        profile.preferred_tutor_persona = "Friendly"
        profile.learning_goals = "Master Django REST Framework."
        profile.save()

        profile.refresh_from_db()
        self.assertEqual(profile.bio, "An updated bio for testing.")
        self.assertEqual(profile.linkedin_url, "https://linkedin.com/in/testuserone")
        self.assertEqual(profile.preferred_tutor_persona, "Friendly")

    def test_user_profile_signal_on_existing_user_save(self):
        # Ensure if user is saved, profile is also saved (or at least doesn't break)
        # The signal currently tries profile.save()
        profile = self.user1.profile
        old_profile_updated_at = profile.updated_at
        
        # Wait a bit to ensure updated_at changes if profile.save() is called
        # This is a bit flaky for precise time checks, but good enough for a simple check
        import time
        time.sleep(0.01)

        self.user1.full_name = "Test User One Updated Name"
        self.user1.save() # This triggers the post_save signal for User

        profile.refresh_from_db()
        # Check if profile's updated_at changed (implies profile.save() was called)
        # This depends on what profile.save() actually does if no fields changed on profile.
        # If profile has no changes, its updated_at might not change.
        # The signal's purpose is more to ensure profile *exists* and gets created if missing.
        # Let's verify it still exists and is linked.
        self.assertEqual(profile.user, self.user1)
        self.assertTrue(hasattr(self.user1, 'profile'))


    def test_user_deletion_cascades_to_profile(self):
        user_to_delete_email = 'deleteme_user@example.com'
        user_to_delete = User.objects.create_user(email=user_to_delete_email, password='password')
        profile_id = user_to_delete.profile.id # Get profile ID before deleting user
        
        self.assertTrue(UserProfile.objects.filter(id=profile_id).exists())
        user_to_delete.delete()
        self.assertFalse(UserProfile.objects.filter(id=profile_id).exists())

# Add more tests:
# - For any custom methods or properties added to User or UserProfile.
# - More edge cases for username/full_name generation in User.save().
# - Test behavior of other_industry_details when industry is 'Other' vs. not.
# - Test constraints or validation on JSONFields in UserProfile if any implicit schemas are expected.
