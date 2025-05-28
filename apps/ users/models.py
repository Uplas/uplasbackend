import uuid
import random
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings # For project-wide choices if any
from django.db.models.signals import post_save
from django.dispatch import receiver
import re # For username generation

# Assuming BaseModel is in apps.core.models
from apps.core.models import BaseModel # Import your BaseModel

# Choices (keeping them here for now, but could be moved to a choices.py or settings)
INDUSTRY_CHOICES = [
    ('Technology', _('Technology')),
    ('Healthcare', _('Healthcare')),
    ('Finance & Banking', _('Finance & Banking')),
    ('Education', _('Education')),
    ('Manufacturing & Engineering', _('Manufacturing & Engineering')),
    ('Retail & E-commerce', _('Retail & E-commerce')),
    ('Marketing & Advertising', _('Marketing & Advertising')),
    ('Arts & Entertainment', _('Arts & Entertainment')),
    ('Student', _('Student (General)')),
    ('Other', _('Other')),
]

LANGUAGE_CHOICES = [
    ('en', _('English')),
    ('es', _('Spanish')),
    ('fr', _('French')),
]

CURRENCY_CHOICES = settings.CURRENCY_CHOICES # Use from settings directly

# Custom User Manager
class UserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """
    def _generate_unique_username(self, email_prefix):
        """
        Generates a unique username based on email prefix.
        Ensures username is valid (alphanumeric, periods, hyphens, underscores)
        and does not exceed 150 characters.
        """
        # Sanitize email_prefix to allow only valid username characters
        # Keep letters, digits, and @/./+/-/_
        sanitized_prefix = re.sub(r'[^\w.@+-]', '', email_prefix)
        
        # Ensure the base prefix is not too long
        base_username = sanitized_prefix[:130] # Reserve space for suffix

        # Attempt 1: Simple numeric suffix
        temp_username = f"{base_username}_{random.randint(1000, 9999)}"
        if not User.objects.filter(username=temp_username).exists():
            return temp_username

        # Attempt 2: Shorter numeric suffix if first was too long or collided
        temp_username = f"{base_username[:135]}_{random.randint(100, 999)}"
        if not User.objects.filter(username=temp_username).exists():
            return temp_username
            
        # Attempt 3: Short UUID suffix as a more robust fallback
        # Ensure the final username does not exceed 150 characters.
        # Max length of UUID hex is 32. We use 8 chars.
        # Max prefix length = 150 - 1 (for underscore) - 8 (for short_uuid) = 141
        prefix_for_uuid = base_username[:141]
        while True:
            short_uuid = uuid.uuid4().hex[:8] # Use 8 chars for better uniqueness
            username = f"{prefix_for_uuid}_{short_uuid}"
            if not User.objects.filter(username=username).exists():
                return username

    def create_user(self, email, password, username=None, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)

        if not username:
            email_prefix = email.split('@')[0]
            username = self._generate_unique_username(email_prefix)
        
        # Ensure username is explicitly set in extra_fields if passed, or use generated.
        extra_fields.setdefault('username', username)
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, username=None, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True) # Superusers should be active by default

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        
        # For superuser, if username is not provided, generate it but ensure it's predictable or simple.
        # However, for CLI creation, username is usually prompted.
        # The AbstractUser.REQUIRED_FIELDS includes 'username', so it must be present.
        if not username:
             email_prefix = email.split('@')[0]
             # A simpler approach for superuser if direct creation, ensure it's unique.
             # For createsuperuser command, Django handles prompting for username.
             # This manager method might be called programmatically.
             username = self._generate_unique_username(email_prefix)


        return self.create_user(email, password, username=username, **extra_fields)


class User(AbstractUser):
    """
    Custom User model inheriting from AbstractUser.
    Uses email as the primary identifier for authentication.
    """
    # Username: Still required by Django's AbstractUser, but we auto-generate it if not provided.
    # Email is the primary login field (USERNAME_FIELD).
    username = models.CharField(
        _('username'),
        max_length=150,
        unique=True,
        help_text=_('Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'),
        validators=[AbstractUser.username_validator],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
        db_index=True # Added for performance as suggested
    )
    email = models.EmailField(
        _('email address'),
        unique=True,
        help_text=_("Required. Will be used for login."),
        db_index=True # Added for performance
    )

    # Personal Information
    full_name = models.CharField(_("Full Name"), max_length=255, blank=True)

    organization = models.CharField(_("Organization/College/School"), max_length=255, blank=True, null=True)
    industry = models.CharField(
        _("Primary Industry/Field of Study"),
        max_length=100,
        choices=INDUSTRY_CHOICES,
        blank=True,
        null=True,
        db_index=True # Added for potential filtering
    )
    other_industry_details = models.CharField(
        _("Other Industry Details"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Specify if 'Other' is selected for industry.")
    )
    profession = models.CharField(_("Current or Target Profession"), max_length=255, blank=True, null=True)

    # Contact Information
    whatsapp_number = models.CharField(
        _("WhatsApp Number (with country code)"),
        max_length=20,
        unique=True, # Ensures uniqueness at DB level
        blank=True,
        null=True,
        db_index=True # Added for performance
    )
    is_whatsapp_verified = models.BooleanField(_("WhatsApp Verified"), default=False)
    whatsapp_verification_code = models.CharField(_("WhatsApp Verification Code"), max_length=6, blank=True, null=True)
    whatsapp_code_created_at = models.DateTimeField(_("WhatsApp Code Created At"), null=True, blank=True)

    # Preferences
    preferred_language = models.CharField(
        _("Preferred Language"),
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='en',
        db_index=True # Added for potential filtering
    )
    preferred_currency = models.CharField(
        _("Preferred Currency"),
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='USD'
    )
    profile_picture_url = models.URLField(_("Profile Picture URL"), max_length=1024, blank=True, null=True)

    # Platform Specific
    career_interest = models.CharField(
        _("Career Interest"),
        max_length=255,
        blank=True,
        null=True,
    )
    uplas_xp_points = models.PositiveIntegerField(_("Uplas XP Points"), default=0)

    # Denormalized field: Updated by payments app (webhooks/signals)
    is_premium_subscriber = models.BooleanField(
        _("Is Premium Subscriber"),
        default=False,
        db_index=True, # Added for performance
        help_text=_("Denormalized field. Single source of truth is the UserSubscription model.")
    )
    
    country = models.CharField(_("Country"), max_length=100, blank=True, null=True, db_index=True)
    city = models.CharField(_("City"), max_length=100, blank=True, null=True)

    # Stripe Customer ID can live directly on User model if UserProfile is not always guaranteed
    # or for simplification. This seems to be the case here based on original feedback.
    stripe_customer_id = models.CharField(
        max_length=255, blank=True, null=True,
        help_text=_("Stripe Customer ID, managed by the payments system."),
        db_index=True # Added for performance
    )

    # Timestamps from AbstractUser: date_joined, last_login
    # Explicit timestamps for record creation/update if BaseModel is not used by User directly.
    created_at = models.DateTimeField(auto_now_add=True, editable=False, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, editable=False, null=True, blank=True)


    USERNAME_FIELD = 'email'
    # Username is still in REQUIRED_FIELDS because AbstractUser includes it.
    # If username were not used at all (even for admin), one might create a custom AbstractBaseUser.
    REQUIRED_FIELDS = ['username'] 

    objects = UserManager()

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-created_at', 'email']


    def save(self, *args, **kwargs):
        # Populate full_name from first_name and last_name if not set
        if not self.full_name and (self.first_name or self.last_name):
            self.full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        
        # Ensure username is populated if created outside custom manager and is empty
        # This is a fallback; UserManager should ideally handle all user creations.
        if not self.username and self.email:
            email_prefix = self.email.split('@')[0]
            # Use the manager's method to generate username to ensure consistency and uniqueness logic
            self.username = User.objects._generate_unique_username(email_prefix)
            
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
        
    def generate_whatsapp_code(self):
        """Generates a 6-digit verification code for WhatsApp and saves it."""
        self.whatsapp_verification_code = str(random.randint(100000, 999999))
        self.whatsapp_code_created_at = timezone.now()
        self.save(update_fields=['whatsapp_verification_code', 'whatsapp_code_created_at'])
        return self.whatsapp_verification_code


class UserProfile(BaseModel): # Inherits UUID id, created_at, updated_at from BaseModel
    """
    Stores additional profile information related to a User.
    Linked OneToOne with the User model.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='profile', 
        verbose_name=_('User')
    )
    bio = models.TextField(_("Short Bio / Professional Summary"), blank=True, null=True)
    
    linkedin_url = models.URLField(_("LinkedIn Profile URL"), blank=True, null=True, max_length=500)
    github_url = models.URLField(_("GitHub Profile URL"), blank=True, null=True, max_length=500)
    website_url = models.URLField(_("Personal Website/Portfolio URL"), blank=True, null=True, max_length=500)

    # AI Personalization Preferences
    preferred_tutor_persona = models.CharField(
        _("Preferred AI Tutor Persona"), max_length=50, blank=True, null=True,
        help_text=_("e.g., Formal, Friendly, Technical, Socratic, Humorous")
    )
    preferred_tts_voice_character = models.CharField(
        _("Preferred TTS Voice Character"), max_length=50, blank=True, null=True,
        help_text=_("e.g., alloy, echo, fable, onyx, nova, shimmer (from OpenAI TTS)")
    )
    preferred_ttv_instructor = models.CharField(
        _("Preferred TTV Instructor"), max_length=20,
        choices=[('uncle_trevor', _('Uncle Trevor')), ('susan', _('Susan'))], # Example choices
        blank=True, null=True
    )
    learning_style_preference = models.JSONField(
        _("Learning Style Preferences (e.g., VARK)"), blank=True, null=True, default=dict,
        help_text=_("Example: {'visual': 0.7, 'auditory': 0.5, 'kinesthetic': 0.3, 'reading_writing': 0.6}")
    )
    areas_of_interest = models.JSONField( # Consider ManyToMany to a Tag/Skill model if these become structured
        _("Specific Areas of Interest for Learning"), blank=True, null=True, default=list,
        help_text=_("List of topics or fields, e.g., ['NLP', 'Computer Vision', 'Web Security']")
    )
    current_knowledge_level = models.JSONField( # Similarly, could be structured with a Skill model
        _("Self-Assessed Knowledge Levels per Topic/Skill"), blank=True, null=True, default=dict,
        help_text=_("Example: {'python-basics': 'Advanced', 'ml-intro': 'Beginner', 'api-design': 'Intermediate'}")
    )
    learning_goals = models.TextField(
        _("User's Stated Learning Goals or Objectives"),
        blank=True, null=True,
        help_text=_("What the user wants to achieve on the platform.")
    )

    # Timestamps (created_at, updated_at) are inherited from BaseModel

    class Meta:
        verbose_name = _('User Profile')
        verbose_name_plural = _('User Profiles')
        ordering = ['-user__date_joined'] # Order by when the associated user joined

    def __str__(self):
        return f"{self.user.email}'s Profile"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile_receiver(sender, instance, created, **kwargs):
    """
    Ensures a UserProfile exists for every User.
    If the User model is updated, this signal also attempts to save the profile,
    which can be useful if UserProfile has denormalized fields from User.
    """
    if created:
        UserProfile.objects.create(user=instance)
    else:
        # Ensure profile exists and save it (e.g., if User model fields trigger profile updates)
        # Using try-except for robustness, though profile should ideally always exist for existing users.
        try:
            # instance.profile.save() # This would be if UserProfile needs to update itself based on User save
            # For now, just ensure it exists
            if not hasattr(instance, 'profile'):
                 UserProfile.objects.create(user=instance)
            else:
                # If you had logic where UserProfile denormalizes User fields,
                # you might want to update and save instance.profile here.
                # For now, the primary goal is creation on user creation.
                pass
        except UserProfile.DoesNotExist: # Should not happen if created=False and signal worked on creation
            UserProfile.objects.create(user=instance)
