import uuid
import random
import re
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import BaseModel

# Industry Choices (Ensure these match your project's needs)
INDUSTRY_CHOICES = [
    ('Technology', _('Technology')),
    ('Finance', _('Finance')),
    ('Healthcare', _('Healthcare')),
    ('Education', _('Education')),
    ('Retail', _('Retail')),
    ('Manufacturing', _('Manufacturing')),
    ('Consulting', _('Consulting')),
    ('Government', _('Government')),
    ('Non-Profit', _('Non-Profit')),
    ('Other', _('Other')),
]

# Language Choices
LANGUAGE_CHOICES = [
    ('en', _('English')),
    ('es', _('Spanish')),
    ('fr', _('French')),
    ('de', _('German')),
    ('zh', _('Chinese')),
    ('ja', _('Japanese')),
    ('pt', _('Portuguese')),
    ('ru', _('Russian')),
    ('ar', _('Arabic')),
    ('hi', _('Hindi')),
]


class UserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier
    and username is auto-generated and unique.
    """
    def _generate_unique_username(self, email_prefix):
        """
        Generates a unique username based on email prefix, ensuring validity
        and uniqueness by appending a short UUID if necessary.
        """
        sanitized_prefix = re.sub(r'[^\w]', '', email_prefix.split('@')[0])
        base_username = sanitized_prefix[:141] # Max 150 - 8 (uuid) - 1 (_)
        if not base_username:
            base_username = "user"

        # Try with a random number first
        username_attempt = f"{base_username}_{random.randint(1000, 9999)}"
        if len(username_attempt) <= 150 and not self.model.objects.filter(username=username_attempt).exists():
            return username_attempt

        # Fallback to UUID
        while True:
            short_uuid = uuid.uuid4().hex[:8]
            username = f"{base_username}_{short_uuid}"
            if len(username) > 150:
                 username = f"{base_username[:141]}_{short_uuid}" # Re-truncate if somehow too long

            if not self.model.objects.filter(username=username).exists():
                return username

    def create_user(self, email, password, username=None, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)

        if not username:
            username = self._generate_unique_username(email)

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
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        if not username:
            username = self._generate_unique_username(email.split('@')[0] or "admin")

        return self.create_user(email, password, username=username, **extra_fields)


class User(AbstractUser):
    """
    Custom User Model extending AbstractUser.
    Email is the primary identifier (USERNAME_FIELD).
    Includes personalization fields and WhatsApp verification.
    """
    username = models.CharField(
        _('username'),
        max_length=150,
        unique=True,
        help_text=_('Required. 150 characters or fewer. Letters, digits and _ only.'),
        error_messages={'unique': _("A user with that username already exists.")},
        db_index=True
    )
    email = models.EmailField(
        _('email address'),
        unique=True,
        help_text=_("Required. Will be used for login."),
        db_index=True
    )
    full_name = models.CharField(_("Full Name"), max_length=255, blank=True)
    organization = models.CharField(_("Organization/College/School"), max_length=255, blank=True, null=True)
    industry = models.CharField(
        _("Primary Industry/Field of Study"),
        max_length=100,
        choices=INDUSTRY_CHOICES,
        blank=True,
        null=True,
        db_index=True
    )
    other_industry_details = models.CharField(
        _("Other Industry Details"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Specify if 'Other' is selected for industry.")
    )
    profession = models.CharField(_("Current or Target Profession"), max_length=255, blank=True, null=True)
    whatsapp_number = models.CharField(
        _("WhatsApp Number (with country code)"),
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        db_index=True
    )
    is_whatsapp_verified = models.BooleanField(_("WhatsApp Verified"), default=False)
    whatsapp_verification_code = models.CharField(_("WhatsApp Verification Code"), max_length=6, blank=True, null=True)
    whatsapp_code_created_at = models.DateTimeField(_("WhatsApp Code Created At"), null=True, blank=True)
    preferred_language = models.CharField(
        _("Preferred Language"),
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='en',
        db_index=True
    )
    preferred_currency = models.CharField(
        _("Preferred Currency"),
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
        default='USD'
    )
    profile_picture_url = models.URLField(_("Profile Picture URL"), max_length=1024, blank=True, null=True)
    career_interest = models.CharField(_("Career Interest"), max_length=255, blank=True, null=True)
    uplas_xp_points = models.PositiveIntegerField(_("Uplas XP Points"), default=0)
    is_premium_subscriber = models.BooleanField(
        _("Is Premium Subscriber"),
        default=False,
        db_index=True,
        help_text=_("Denormalized field. Single source of truth is the UserSubscription model.")
    )
    country = models.CharField(_("Country"), max_length=100, blank=True, null=True, db_index=True)
    city = models.CharField(_("City"), max_length=100, blank=True, null=True)
    stripe_customer_id = models.CharField(
        max_length=255, blank=True, null=True,
        help_text=_("Stripe Customer ID, managed by the payments system."),
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, editable=False, null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username'] # 'username' is still required as it's unique and used.

    objects = UserManager()

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-created_at', 'email']

    def save(self, *args, **kwargs):
        """
        Populate full_name if empty and ensure username exists.
        """
        if not self.full_name and (self.first_name or self.last_name):
            self.full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()

        if not self.username and self.email:
            self.username = User.objects._generate_unique_username(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

    def generate_whatsapp_code(self):
        """
        Generates a 6-digit WhatsApp verification code, sets its creation time,
        and saves these specific fields.
        """
        self.whatsapp_verification_code = str(random.randint(100000, 999999))
        self.whatsapp_code_created_at = timezone.now()
        self.save(update_fields=['whatsapp_verification_code', 'whatsapp_code_created_at', 'updated_at'])
        return self.whatsapp_verification_code


class UserProfile(BaseModel):
    """
    Extends the User model with additional profile information,
    including learning preferences and external links.
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
    preferred_tutor_persona = models.CharField(
        _("Preferred AI Tutor Persona"), max_length=50, blank=True, null=True,
        help_text=_("e.g., Formal, Friendly, Technical, Socratic, Humorous")
    )
    preferred_tts_voice_character = models.CharField(
        _("Preferred TTS Voice Character"), max_length=50, blank=True, null=True,
        help_text=_("e.g., alloy, echo, fable, onyx, nova, shimmer")
    )
    preferred_ttv_instructor = models.CharField(
        _("Preferred TTV Instructor"), max_length=20,
        choices=[('uncle_trevor', _('Uncle Trevor')), ('susan', _('Susan'))],
        blank=True, null=True
    )
    learning_style_preference = models.JSONField(
        _("Learning Style Preferences (e.g., VARK)"), blank=True, null=True, default=dict,
        help_text=_("Example: {'visual': 0.7, 'auditory': 0.5}")
    )
    areas_of_interest = models.JSONField(
        _("Specific Areas of Interest for Learning"), blank=True, null=True, default=list,
        help_text=_("Example: ['NLP', 'Web Security']")
    )
    current_knowledge_level = models.JSONField(
        _("Self-Assessed Knowledge Levels per Topic/Skill"), blank=True, null=True, default=dict,
        help_text=_("Example: {'python-basics': 'Advanced', 'ml-intro': 'Beginner'}")
    )
    learning_goals = models.TextField(
        _("User's Stated Learning Goals or Objectives"),
        blank=True, null=True,
        help_text=_("What the user wants to achieve on the platform.")
    )

    class Meta:
        verbose_name = _('User Profile')
        verbose_name_plural = _('User Profiles')
        ordering = ['-user__created_at'] # Order by user creation time

    def __str__(self):
        return f"{self.user.email}'s Profile"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Signal receiver to create a UserProfile when a User is created,
    and ensure it exists on update.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance)
    else:
        # Ensures profile exists if somehow deleted or not created before.
        UserProfile.objects.get_or_create(user=instance)
