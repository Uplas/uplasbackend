import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

from .models import UserProfile, INDUSTRY_CHOICES, LANGUAGE_CHOICES

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserProfile model.
    """
    class Meta:
        model = UserProfile
        fields = [
            'bio', 'linkedin_url', 'github_url', 'website_url',
            'preferred_tutor_persona', 'preferred_tts_voice_character',
            'preferred_ttv_instructor', 'learning_style_preference',
            'areas_of_interest', 'current_knowledge_level', 'learning_goals',
            'created_at', 'updated_at'
        ]
        read_only_fields = ('created_at', 'updated_at')


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model, including nested UserProfile.
    Used for retrieving and updating user details.
    """
    profile = UserProfileSerializer(required=False, partial=True)
    industry_display = serializers.CharField(source='get_industry_display', read_only=True)
    preferred_language_display = serializers.CharField(source='get_preferred_language_display', read_only=True)
    preferred_currency_display = serializers.CharField(source='get_preferred_currency_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name', 'first_name', 'last_name',
            'organization', 'industry', 'industry_display', 'other_industry_details', 'profession',
            'whatsapp_number', 'is_whatsapp_verified',
            'preferred_language', 'preferred_language_display',
            'preferred_currency', 'preferred_currency_display',
            'profile_picture_url', 'career_interest', 'uplas_xp_points',
            'is_premium_subscriber', 'country', 'city', 'stripe_customer_id',
            'profile', 'is_staff', 'is_active', 'date_joined', 'last_login',
            'created_at', 'updated_at', 'password' # Include password for write_only
        ]
        read_only_fields = (
            'id', 'username', 'is_whatsapp_verified', 'uplas_xp_points',
            'is_premium_subscriber', 'stripe_customer_id', 'is_staff',
            'date_joined', 'last_login', 'created_at', 'updated_at',
            'industry_display', 'preferred_language_display', 'preferred_currency_display'
        )
        extra_kwargs = {
            'email': {'required': False},
            'password': {'write_only': True, 'required': False, 'style': {'input_type': 'password'}},
            'first_name': {'required': False},
            'last_name': {'required': False},
        }

    def validate_industry(self, value):
        """
        Validate that 'other_industry_details' is provided if 'Other' is selected.
        """
        other_details = self.initial_data.get('other_industry_details', '').strip()
        if value == 'Other' and not other_details:
            raise serializers.ValidationError(_("Please specify details if 'Other' industry is selected."))
        return value

    def validate_whatsapp_number(self, value):
        """
        Validate WhatsApp number format and uniqueness.
        """
        if value:
            if not re.match(r"^\+[1-9]\d{1,14}$", value):
                raise serializers.ValidationError(_("WhatsApp number must be in E.164 format, e.g., +1234567890."))

            query = User.objects.filter(whatsapp_number=value)
            if self.instance: # Exclude self during update
                query = query.exclude(pk=self.instance.pk)

            if query.exists():
                raise serializers.ValidationError(_("This WhatsApp number is already registered."))
        return value

    def update(self, instance, validated_data):
        """
        Handle updates for User and nested UserProfile.
        """
        profile_data = validated_data.pop('profile', None)
        password = validated_data.pop('password', None)

        if password:
            instance.set_password(password)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if validated_data.get('industry') and validated_data.get('industry') != 'Other':
            instance.other_industry_details = None

        instance.save()

        if profile_data is not None:
            profile_instance = instance.profile
            profile_serializer = UserProfileSerializer(profile_instance, data=profile_data, partial=True)
            profile_serializer.is_valid(raise_exception=True)
            profile_serializer.save()

        return instance


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration. Handles password creation and validation.
    """
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password], style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ('email', 'password', 'password_confirm', 'first_name', 'last_name', 'full_name')

    def validate(self, attrs):
        """
        Validate that passwords match.
        """
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": _("Password fields didn't match.")})
        return attrs

    def create(self, validated_data):
        """
        Create a new user with a hashed password.
        """
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer for changing the user's password.
    Requires old password and new password confirmation.
    """
    old_password = serializers.CharField(required=True, style={'input_type': 'password'})
    new_password = serializers.CharField(required=True, validators=[validate_password], style={'input_type': 'password'})
    new_password_confirm = serializers.CharField(required=True, style={'input_type': 'password'})

    def validate_old_password(self, value):
        """
        Validate the old password.
        """
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Your old password was entered incorrectly."))
        return value

    def validate(self, data):
        """
        Validate that new passwords match and are different from the old one.
        """
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': _("The two new password fields didn't match.")})
        if data['new_password'] == data['old_password']:
             raise serializers.ValidationError({'new_password': _("New password cannot be the same as the old password.")})
        return data

    def save(self, **kwargs):
        """
        Save the new password for the user.
        """
        password = self.validated_data['new_password']
        user = self.context['request'].user
        user.set_password(password)
        user.save(update_fields=['password', 'updated_at'])
        return user


class SendWhatsAppVerificationSerializer(serializers.Serializer):
    """
    Serializer to request sending a WhatsApp verification code.
    Validates the phone number format.
    """
    whatsapp_number = serializers.CharField(required=True)

    def validate_whatsapp_number(self, value):
        """
        Validate WhatsApp number format and uniqueness (excluding current user).
        """
        if not re.match(r"^\+[1-9]\d{1,14}$", value):
            raise serializers.ValidationError(_("WhatsApp number must be in E.164 format, e.g., +1234567890."))

        query = User.objects.filter(whatsapp_number=value)
        user = self.context['request'].user
        if user:
             query = query.exclude(pk=user.pk)

        if query.exists():
            raise serializers.ValidationError(_("This WhatsApp number is already registered with another account."))
        return value


class VerifyWhatsAppSerializer(serializers.Serializer):
    """
    Serializer to verify the WhatsApp code sent to the user.
    """
    code = serializers.CharField(required=True, min_length=6, max_length=6)

    def validate_code(self, value):
        """
        Validate the verification code against the user's stored code and expiry.
        """
        user = self.context['request'].user
        code_expiry_minutes = getattr(settings, 'WHATSAPP_CODE_EXPIRY_MINUTES', 10)

        if not user.whatsapp_verification_code or user.whatsapp_verification_code != value:
            raise serializers.ValidationError(_("Invalid verification code."))

        if user.whatsapp_code_created_at and \
           timezone.now() > user.whatsapp_code_created_at + timedelta(minutes=code_expiry_minutes):
            raise serializers.ValidationError(_("Verification code has expired. Please request a new one."))

        return value
