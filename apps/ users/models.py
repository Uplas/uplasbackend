from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings # For project-wide choices if any
from django.utils import timezone # For whatsapp_code_created_at
import random

# Industry Choices from Uplas Backend Integration Guide 
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

# Language Choices from Uplas Backend Integration Guide 
# Match with frontend: locales/en.json, es.json, fr.json 
LANGUAGE_CHOICES = [
    ('en', _('English')),
    ('es', _('Spanish')), # Frontend uses "Spanish"
    ('fr', _('French')),  # Frontend uses "French"
]

# Currency Choices from Uplas Backend Integration Guide 
CURRENCY_CHOICES = [
    ('USD', _('USD - US Dollar')),
    ('EUR', _('EUR - Euro')),
    ('GBP', _('GBP - British Pound')),
    ('KES', _('KES - Kenyan Shilling')),
    ('INR', _('INR - Indian Rupee')),
]

class User(AbstractUser):
    email = models.EmailField(_('email address'), unique=True)

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

    whatsapp_number = models.CharField(_("WhatsApp Number (with country code)"), max_length=20, unique=True, blank=True, null=True)
    is_whatsapp_verified = models.BooleanField(_("WhatsApp Verified"), default=False)
    whatsapp_verification_code = models.CharField(_("WhatsApp Verification Code"), max_length=6, blank=True, null=True)
    whatsapp_code_created_at = models.DateTimeField(_("WhatsApp Code Created At"), null=True, blank=True)

    preferred_language = models.CharField(
        _("Preferred Language"),
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='en'
    )
    preferred_currency = models.CharField(
        _("Preferred Currency"),
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='USD'
    )
    profile_picture_url = models.URLField(_("Profile Picture URL"), max_length=1024, blank=True, null=True)

    career_interest = models.CharField(
        _("Career Interest"),
        max_length=255,
        blank=True,
        null=True,
    )
    uplas_xp_points = models.PositiveIntegerField(_("Uplas XP Points"), default=0)

    is_premium_subscriber = models.BooleanField(_("Is Premium Subscriber"), default=False)
    subscription_plan_name = models.CharField(_("Current Plan Name (Denormalized)"), max_length=100, blank=True, null=True)
    subscription_end_date = models.DateField(_("Subscription End Date"), null=True, blank=True)

    country = models.CharField(_("Country"), max_length=100, blank=True, null=True)
    city = models.CharField(_("City"), max_length=100, blank=True, null=True)

    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stripe Customer ID")

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        if not self.full_name and (self.first_name or self.last_name):
            self.full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        if not self.username:
             self.username = self.email.split('@')[0] + "_" + str(random.randint(1000,9999))
             while User.objects.filter(username=self.username).exists():
                 self.username = self.email.split('@')[0] + "_" + str(random.randint(1000,9999))
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
        
    def generate_whatsapp_code(self):
        self.whatsapp_verification_code = str(random.randint(100000, 999999))
        self.whatsapp_code_created_at = timezone.now()
        self.save(update_fields=['whatsapp_verification_code', 'whatsapp_code_created_at'])
        return self.whatsapp_verification_code

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(_("Short Bio"), blank=True, null=True)
    linkedin_url = models.URLField(_("LinkedIn Profile URL"), blank=True, null=True)
    github_url = models.URLField(_("GitHub Profile URL"), blank=True, null=True)
    website_url = models.URLField(_("Personal Website/Portfolio"), blank=True, null=True)

    preferred_tutor_persona = models.CharField(
        _("Preferred AI Tutor Persona"), max_length=50, blank=True, null=True,
        help_text=_("e.g., Formal, Friendly, Technical, Socratic")
    )
    preferred_tts_voice_character = models.CharField(
        _("Preferred TTS Voice Character"), max_length=50, blank=True, null=True,
        help_text=_("e.g., alloy, echo, fable, onyx, nova, shimmer")
    )
    preferred_ttv_instructor = models.CharField(
        _("Preferred TTV Instructor"), max_length=20,
        choices=[('uncle_trevor', 'Uncle Trevor'), ('susan', 'Susan')],
        blank=True, null=True
    )
    learning_style_preference = models.JSONField(
        _("Learning Style Preferences"), blank=True, null=True, default=dict,
        help_text=_("e.g., {'visual': 0.7, 'auditory': 0.5, 'kinesthetic': 0.3, 'reading_writing': 0.6}")
    )
    areas_of_interest = models.JSONField(
        _("Specific Areas of Interest"), blank=True, null=True, default=list,
        help_text=_("e.g., ['NLP', 'Computer Vision', 'Reinforcement Learning']")
    )
    current_knowledge_level = models.JSONField(
        _("Self-Assessed Knowledge Levels"), blank=True, null=True, default=dict,
        help_text=_("e.g., {'python-basics': 'Advanced', 'ml-intro': 'Intermediate'}")
    )
    learning_goals = models.TextField(_("User's Stated Learning Goals"), blank=True, null=True)

    # Stripe Customer ID is now on the User model itself.
    # If you had it here and want to keep it for some reason, uncomment below:
    # stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stripe Customer ID")


    def __str__(self):
        return f"{self.user.email}'s Profile"

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    try:
        instance.profile.save() # Ensure profile exists and is saved if user is updated
    except UserProfile.DoesNotExist:
        UserProfile.objects.create(user=instance) # Safeguard
