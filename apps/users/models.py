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

INDUSTRY_CHOICES = [
    ('Technology', _('Technology')), ('Finance', _('Finance')), ('Healthcare', _('Healthcare')),
    ('Education', _('Education')), ('Retail', _('Retail')), ('Manufacturing', _('Manufacturing')),
    ('Consulting', _('Consulting')), ('Government', _('Government')), ('Non-Profit', _('Non-Profit')),
    ('Other', _('Other')),
]

LANGUAGE_CHOICES = [
    ('en', _('English')), ('es', _('Spanish')), ('fr', _('French')), ('de', _('German')),
    ('zh', _('Chinese')), ('ja', _('Japanese')), ('pt', _('Portuguese')), ('ru', _('Russian')),
    ('ar', _('Arabic')), ('hi', _('Hindi')),
]

class UserManager(BaseUserManager):
    def _generate_unique_username(self, email_prefix):
        sanitized_prefix = re.sub(r'[^\w]', '', email_prefix.split('@')[0])
        base_username = sanitized_prefix[:141]
        if not base_username: base_username = "user"
        username_attempt = f"{base_username}_{random.randint(1000, 9999)}"
        if not self.model.objects.filter(username=username_attempt).exists():
            return username_attempt
        while True:
            short_uuid = uuid.uuid4().hex[:8]
            username = f"{base_username}_{short_uuid}"
            if not self.model.objects.filter(username=username).exists():
                return username

    def create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        if 'username' not in extra_fields:
            extra_fields['username'] = self._generate_unique_username(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_('email address'), unique=True, db_index=True)
    full_name = models.CharField(_("Full Name"), max_length=255, blank=True)
    organization = models.CharField(_("Organization/College/School"), max_length=255, blank=True, null=True)
    industry = models.CharField(_("Industry"), max_length=100, choices=INDUSTRY_CHOICES, blank=True, null=True, db_index=True)
    other_industry_details = models.CharField(_("Other Industry Details"), max_length=255, blank=True, null=True)
    profession = models.CharField(_("Profession"), max_length=255, blank=True, null=True)
    whatsapp_number = models.CharField(_("WhatsApp Number"), max_length=20, unique=True, blank=True, null=True, db_index=True)
    is_whatsapp_verified = models.BooleanField(_("WhatsApp Verified"), default=False)
    whatsapp_verification_code = models.CharField(_("WhatsApp Code"), max_length=6, blank=True, null=True)
    whatsapp_code_created_at = models.DateTimeField(_("WhatsApp Code Created At"), null=True, blank=True)
    preferred_language = models.CharField(_("Language"), max_length=10, choices=LANGUAGE_CHOICES, default='en', db_index=True)
    preferred_currency = models.CharField(_("Currency"), max_length=3, choices=settings.CURRENCY_CHOICES, default='USD')
    profile_picture_url = models.URLField(_("Profile Picture URL"), max_length=1024, blank=True, null=True)
    uplas_xp_points = models.PositiveIntegerField(_("XP Points"), default=0)
    is_premium_subscriber = models.BooleanField(_("Is Premium"), default=False, db_index=True)
    country = models.CharField(_("Country"), max_length=100, blank=True, null=True, db_index=True)
    city = models.CharField(_("City"), max_length=100, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    
    # We no longer need created_at and updated_at as AbstractUser has date_joined and we can use auto_now
    # We will use date_joined from AbstractUser as the creation timestamp.

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = UserManager()

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-date_joined']

    def save(self, *args, **kwargs):
        if not self.full_name and (self.first_name or self.last_name):
            self.full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

class UserProfile(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(_("Bio"), blank=True, null=True)
    linkedin_url = models.URLField(_("LinkedIn URL"), blank=True, null=True)
    github_url = models.URLField(_("GitHub URL"), blank=True, null=True)
    website_url = models.URLField(_("Website URL"), blank=True, null=True)
    preferred_tutor_persona = models.CharField(_("Tutor Persona"), max_length=50, blank=True, null=True)
    learning_goals = models.TextField(_("Learning Goals"), blank=True, null=True)
    career_interest = models.CharField(_("Career Interest"), max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = _('User Profile')
        verbose_name_plural = _('User Profiles')

    def __str__(self):
        return f"{self.user.email}'s Profile"

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    instance.profile.save()