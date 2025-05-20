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
# Check frontend for consistency if possible (not explicitly in uploaded files beyond general structure)
CURRENCY_CHOICES = [
    ('USD', _('USD - US Dollar')),
    ('EUR', _('EUR - Euro')),
    ('GBP', _('GBP - British Pound')),
    ('KES', _('KES - Kenyan Shilling')), # Common in Nairobi, Kenya
    ('INR', _('INR - Indian Rupee')),
]

class User(AbstractUser):
    # username, first_name, last_name, email, password, is_staff, is_active, date_joined are inherited
    # Ensure email is unique and used for login as per guide 
    email = models.EmailField(_('email address'), unique=True) # Overriding to ensure unique=True

    full_name = models.CharField(_("Full Name"), max_length=255, blank=True) # Guide mentions full_name
    organization = models.CharField(_("Organization/College/School"), max_length=255, blank=True, null=True) # 
    industry = models.CharField(
        _("Primary Industry/Field of Study"),
        max_length=100,
        choices=INDUSTRY_CHOICES,
        blank=True, # Making it blank=True as per common practice, signup can enforce
        null=True
    ) # 
    other_industry_details = models.CharField(
        _("Other Industry Details"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Specify if 'Other' is selected for industry.")
    ) # 
    profession = models.CharField(_("Current or Target Profession"), max_length=255, blank=True, null=True) # 

    whatsapp_number = models.CharField(_("WhatsApp Number (with country code)"), max_length=20, unique=True, blank=True, null=True) # 
    is_whatsapp_verified = models.BooleanField(_("WhatsApp Verified"), default=False) # 
    whatsapp_verification_code = models.CharField(_("WhatsApp Verification Code"), max_length=6, blank=True, null=True)
    whatsapp_code_created_at = models.DateTimeField(_("WhatsApp Code Created At"), null=True, blank=True)


    preferred_language = models.CharField(
        _("Preferred Language"),
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='en' # Default to English as per guide 
    )
    preferred_currency = models.CharField(
        _("Preferred Currency"),
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='USD' # Default to USD as per guide 
    )
    # Profile picture: URLField initially, can switch to ImageField later with GCS setup
    profile_picture_url = models.URLField(_("Profile Picture URL"), max_length=1024, blank=True, null=True) # 

    career_interest = models.CharField( # From community onboarding in frontend guide 
        _("Career Interest"),
        max_length=255,
        blank=True,
        null=True,
    )
    uplas_xp_points = models.PositiveIntegerField(_("Uplas XP Points"), default=0) # Assuming XP points are positive

    # Subscription Details - To be linked by payments app
    is_premium_subscriber = models.BooleanField(_("Is Premium Subscriber"), default=False)
    subscription_plan_name = models.CharField(_("Current Plan Name (Denormalized)"), max_length=100, blank=True, null=True) # Name of the plan from SubscriptionPlan
    subscription_end_date = models.DateField(_("Subscription End Date"), null=True, blank=True)

    # Location - for personalization
    country = models.CharField(_("Country"), max_length=100, blank=True, null=True)
    city = models.CharField(_("City"), max_length=100, blank=True, null=True)

    # Stripe Customer ID - important for payments
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stripe Customer ID")


    USERNAME_FIELD = 'email' # Use email for login
    REQUIRED_FIELDS = ['username'] # username still required by AbstractUser, but we'll make it non-interactive for users

    def save(self, *args, **kwargs):
        if not self.full_name and (self.first_name or self.last_name): # Ensure full_name is populated
            self.full_name = f"{self.first_name} {self.last_name}".strip()
        if not self.username: # Auto-populate username if not provided (e.g., from email)
             self.username = self.email.split('@')[0] + "_" + str(random.randint(1000,9999))
             while User.objects.filter(username=self.username).exists(): # Ensure uniqueness
                 self.username = self.email.split('@')[0] + "_" + str(random.randint(1000,9999))
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email # More user-friendly than username if email is login
        
    def generate_whatsapp_code(self):
        self.whatsapp_verification_code = str(random.randint(100000, 999999))
        self.whatsapp_code_created_at = timezone.now()
        self.save(update_fields=['whatsapp_verification_code', 'whatsapp_code_created_at']) # Save only specific fields
        return self.whatsapp_verification_code

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(_("Short Bio"), blank=True, null=True)
    linkedin_url = models.URLField(_("LinkedIn Profile URL"), blank=True, null=True)
    github_url = models.URLField(_("GitHub Profile URL"), blank=True, null=True)
    website_url = models.URLField(_("Personal Website/Portfolio"), blank=True, null=True)

    # Preferences for AI Agents
    preferred_tutor_persona = models.CharField(
        _("Preferred AI Tutor Persona"), max_length=50, blank=True, null=True,
        help_text=_("e.g., Formal, Friendly, Technical, Socratic")
    )
    preferred_tts_voice_character = models.CharField( # Maps to frontend character names
        _("Preferred TTS Voice Character"), max_length=50, blank=True, null=True,
        help_text=_("e.g., alloy, echo, fable, onyx, nova, shimmer")
    )
    preferred_ttv_instructor = models.CharField(
        _("Preferred TTV Instructor"), max_length=20,
        choices=[('uncle_trevor', 'Uncle Trevor'), ('susan', 'Susan')],
        blank=True, null=True
    )
    # Data for Personalization
    learning_style_preference = models.JSONField(
        _("Learning Style Preferences"), blank=True, null=True, default=dict,
        help_text=_("e.g., {'visual': 0.7, 'auditory': 0.5, 'kinesthetic': 0.3, 'reading_writing': 0.6}")
    )
    areas_of_interest = models.JSONField( # List of strings
        _("Specific Areas of Interest"), blank=True, null=True, default=list,
        help_text=_("e.g., ['NLP', 'Computer Vision', 'Reinforcement Learning']")
    )
    current_knowledge_level = models.JSONField( # Dict: {'topic_slug_or_id': 'Beginner/Intermediate/Advanced'}
        _("Self-Assessed Knowledge Levels"), blank=True, null=True, default=dict,
        help_text=_("e.g., {'python-basics': 'Advanced', 'ml-intro': 'Intermediate'}")
    )
    learning_goals = models.TextField(_("User's Stated Learning Goals"), blank=True, null=True)

    def __str__(self):
        return f"{self.user.email}'s Profile"

# Signal to create/update UserProfile when User is created/saved
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    try:
        instance.profile.save()
    except UserProfile.DoesNotExist: # Should be caught by created block, but as a safeguard
        UserProfile.objects.create(user=instance)
