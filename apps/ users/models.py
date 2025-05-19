from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import random

# Industry Choices - consider making this a separate model if it needs to be dynamic
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

# Language Choices - align with frontend
LANGUAGE_CHOICES = [
    ('en', _('English')),
    ('es', _('Español')),
    ('fr', _('Français')),
    # Add more as supported
]

# Currency Choices - align with frontend
CURRENCY_CHOICES = [
    ('USD', _('USD - US Dollar')),
    ('EUR', _('EUR - Euro')),
    ('GBP', _('GBP - British Pound')),
    ('KES', _('KES - Kenyan Shilling')),
    ('INR', _('INR - Indian Rupee')),
    # Add more as supported
]

class User(AbstractUser):
    """
    Custom user model extending Django's AbstractUser.
    Based on the Uplas Backend Integration Guide. 
    """
    # username, first_name, last_name, email, password, is_staff, is_active, date_joined are inherited

    full_name = models.CharField(_("Full Name"), max_length=255, blank=True)
    organization = models.CharField(_("Organization/College/School"), max_length=255, blank=True, null=True)
    industry = models.CharField(
        _("Primary Industry/Field of Study"),
        max_length=100,
        choices=INDUSTRY_CHOICES,
        blank=True,
        null=True
    )
    other_industry_details = models.CharField(
        _("Other Industry Details"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Specify if 'Other' is selected for industry.")
    )
    profession = models.CharField(_("Current or Target Profession"), max_length=255, blank=True, null=True)

    # Consider using a dedicated library like phonenumber_field for robust phone number handling
    whatsapp_number = models.CharField(_("WhatsApp Number (with country code)"), max_length=20, unique=True, blank=True, null=True)
    is_whatsapp_verified = models.BooleanField(_("WhatsApp Verified"), default=False)
    whatsapp_verification_code = models.CharField(_("WhatsApp Verification Code"), max_length=6, blank=True, null=True)
    whatsapp_code_created_at = models.DateTimeField(_("WhatsApp Code Created At"), null=True, blank=True)


    preferred_language = models.CharField(
        _("Preferred Language"),
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default=settings.LANGUAGE_CODE # Default to project's language
    )
    preferred_currency = models.CharField(
        _("Preferred Currency"),
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='USD'
    )
    profile_picture_url = models.URLField(_("Profile Picture URL"), max_length=1024, blank=True, null=True)
    # For ImageField, ensure Pillow is installed and MEDIA_ROOT/MEDIA_URL are configured
    # profile_picture = models.ImageField(_("Profile Picture"), upload_to='profile_pics/', blank=True, null=True)


    career_interest = models.CharField(
        _("Career Interest (from community onboarding)"),
        max_length=255,
        blank=True,
        null=True,
        # Consider making these choices dynamic or linking to a CareerInterest model
    )
    uplas_xp_points = models.IntegerField(_("Uplas XP Points"), default=0)

    # Subscription Details
    is_premium_subscriber = models.BooleanField(_("Is Premium Subscriber"), default=False)
    # ForeignKey to SubscriptionPlan will be in payments app
    subscription_plan = models.ForeignKey(
        'payments.SubscriptionPlan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscribers'
    )
    subscription_end_date = models.DateField(_("Subscription End Date"), null=True, blank=True)

    # Location - for personalization
    country = models.CharField(_("Country"), max_length=100, blank=True, null=True)
    city = models.CharField(_("City"), max_length=100, blank=True, null=True)


    def save(self, *args, **kwargs):
        if not self.full_name and (self.first_name or self.last_name):
            self.full_name = f"{self.first_name} {self.last_name}".strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username
        
    def generate_whatsapp_code(self):
        self.whatsapp_verification_code = str(random.randint(100000, 999999))
        self.whatsapp_code_created_at = timezone.now()
        self.save()
        return self.whatsapp_verification_code

class UserProfile(models.Model):
    """
    Separate profile to hold additional, potentially optional, user information.
    Can be linked one-to-one with the User model.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(_("Short Bio"), blank=True, null=True)
    linkedin_url = models.URLField(_("LinkedIn Profile URL"), blank=True, null=True)
    github_url = models.URLField(_("GitHub Profile URL"), blank=True, null=True)
    website_url = models.URLField(_("Personal Website/Portfolio"), blank=True, null=True)

    # Preferences for AI Agents
    preferred_tutor_persona = models.CharField(
        _("Preferred AI Tutor Persona"),
        max_length=50,
        blank=True,
        null=True,
        help_text=_("e.g., Formal, Friendly, Technical")
    )
    preferred_tts_voice = models.CharField(
        _("Preferred TTS Voice"),
        max_length=50, # Based on voice names like 'alloy', 'echo'
        blank=True,
        null=True
    )
    preferred_ttv_instructor = models.CharField(
        _("Preferred TTV Instructor"),
        max_length=20, # 'uncle_trevor', 'susan'
        choices=[('uncle_trevor', 'Uncle Trevor'), ('susan', 'Susan')],
        blank=True,
        null=True
    )

    # Data for Personalization - collected implicitly or explicitly
    learning_style_preference = models.JSONField(
        _("Learning Style Preferences"),
        blank=True,
        null=True,
        help_text=_("e.g., visual, auditory, kinesthetic, reading/writing - can be a set of scores or dominant style")
    )
    areas_of_interest = models.JSONField(
        _("Specific Areas of Interest within AI"),
        blank=True,
        null=True,
        help_text=_("e.g., ['NLP', 'Computer Vision', 'Reinforcement Learning']")
    )
    current_knowledge_level = models.JSONField(
        _("Self-Assessed Knowledge Levels per Topic/Domain"),
        blank=True,
        null=True,
        help_text=_("e.g., {'Python': 'Advanced', 'Machine Learning Basics': 'Intermediate'}")
    )
    learning_goals = models.TextField(
        _("User's Stated Learning Goals"),
        blank=True,
        null=True
    )
    # Analogies/Examples preferences based on industry, location, career
    # This can be derived from User model fields (industry, profession, country, city)
    # or explicitly asked. For now, we'll derive.

    def __str__(self):
        return f"{self.user.username}'s Profile"

# Signal to create/update UserProfile when User is created/saved
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    instance.profile.save()
