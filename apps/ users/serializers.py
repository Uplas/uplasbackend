from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken # For login response

# Assuming models are in .models of the current app (users)
from .models import UserProfile, INDUSTRY_CHOICES, LANGUAGE_CHOICES, CURRENCY_CHOICES

User = get_user_model()

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserProfile model.
    Used for both displaying and updating profile details.
    """
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', 
            'bio', 'linkedin_url', 'github_url', 'website_url',
            'preferred_tutor_persona', 'preferred_tts_voice_character',
            'preferred_ttv_instructor', 'learning_style_preference',
            'areas_of_interest', 'current_knowledge_level', 'learning_goals',
            'created_at', 'updated_at' 
        ]
        read_only_fields = ('id', 'user', 'created_at', 'updated_at') 

    def update(self, instance, validated_data):
        # Custom update logic if needed, e.g., for JSONFields if they have complex validation
        return super().update(instance, validated_data)


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model.
    Includes nested UserProfile data for comprehensive user representation.
    Used for retrieving user details and updating them (by owner or admin).
    """
    profile = UserProfileSerializer(required=False, allow_null=True) 

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
            'is_premium_subscriber', 
            'country', 'city', 'stripe_customer_id',
            'profile', 
            'is_staff', 'is_active', 'date_joined', 'last_login',
            'created_at', 'updated_at'
        ]
        read_only_fields = (
            'id', 'username', 
            'is_whatsapp_verified', 'uplas_xp_points',
            'is_premium_subscriber', 
            'stripe_customer_id', 
            'is_staff', # Should be managed by admin only
            # 'is_active', # Can be managed by admin; user might deactivate own account via specific flow
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
        if value == 'Other' and not self.initial_data.get('other_industry_details'):
            raise serializers.ValidationError(_("Please specify details if 'Other' industry is selected."))
        return value
    
    def validate_whatsapp_number(self, value):
        if value: # If provided
            if not value.startswith('+'):
                raise serializers.ValidationError(_("WhatsApp number must start with a country code (e.g., +1234567890)."))
            
            # Check for uniqueness if it's being set or changed
            # Model level unique=True handles DB constraint. Serializer check provides earlier feedback.
            query = User.objects.filter(whatsapp_number=value)
            if self.instance: # If updating an existing user
                query = query.exclude(pk=self.instance.pk)
            
            # Check if user is trying to set a number already verified by another user.
            # This logic might be complex depending on if numbers can be transferred or re-verified.
            # if query.filter(is_whatsapp_verified=True).exists():
            #     raise serializers.ValidationError(_("This WhatsApp number is already verified by another active account."))
            if query.exists():
                raise serializers.ValidationError(_("This WhatsApp number is already registered or pending verification with another account."))
        return value


    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)

        # Update User instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update nested UserProfile if data is provided
        if profile_data is not None:
            profile_instance = instance.profile # Profile should exist due to signal
            if profile_instance:
                profile_serializer = UserProfileSerializer(instance.profile, data=profile_data, partial=True, context=self.context)
                if profile_serializer.is_valid(raise_exception=True):
                    profile_serializer.save()
        return instance


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password], 
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    username = serializers.CharField(required=False, allow_blank=True, max_length=150)


    class Meta:
        model = User
        fields = (
            'email', 'username', 'password', 'password_confirm',
            'full_name', 'first_name', 'last_name', 
            'organization', 'industry', 'other_industry_details', 'profession',
            'preferred_language', 'preferred_currency', 'country', 'city',
            'career_interest', 'whatsapp_number' 
        )
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
            'full_name': {'required': False},
            'organization': {'required': False},
            'industry': {'required': False},
            'other_industry_details': {'required': False},
            'profession': {'required': False},
            'preferred_language': {'required': False},
            'preferred_currency': {'required': False},
            'country': {'required': False},
            'city': {'required': False},
            'career_interest': {'required': False},
            'whatsapp_number': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(_("A user with this email address already exists."))
        return value

    def validate_username(self, value):
        if value and User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(_("This username is already taken. Please choose another."))
        return value
    
    def validate_whatsapp_number(self, value):
        if value: 
            if not value.startswith('+'):
                raise serializers.ValidationError(_("WhatsApp number must start with a country code (e.g., +1234567890)."))
            if User.objects.filter(whatsapp_number=value).exists():
                raise serializers.ValidationError(_("This WhatsApp number is already registered."))
        return value

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({"password_confirm": _("Password fields didn't match.")})
        
        industry = attrs.get('industry')
        other_industry_details = attrs.get('other_industry_details')
        if industry == 'Other' and not other_industry_details:
            raise serializers.ValidationError({
                "other_industry_details": _("Please specify details if 'Other' industry is selected.")
            })
        if industry != 'Other' and other_industry_details:
            attrs['other_industry_details'] = None 

        attrs.pop('password_confirm') 
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, style={'input_type': 'password'})
    new_password = serializers.CharField(required=True, validators=[validate_password], style={'input_type': 'password'})
    new_password_confirm = serializers.CharField(required=True, style={'input_type': 'password'})

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Your old password was entered incorrectly. Please enter it again."))
        return value

    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': _("The two new password fields didn't match.")})
        return data

    def save(self, **kwargs): # Renamed from 'update' to 'save' to match Serializer convention
        password = self.validated_data['new_password']
        user = self.context['request'].user
        user.set_password(password)
        user.save(update_fields=['password', 'updated_at']) # Specify fields to update
        return user


class SendWhatsAppVerificationSerializer(serializers.Serializer):
    whatsapp_number = serializers.CharField(max_length=20, required=True)

    def validate_whatsapp_number(self, value):
        if not value.startswith('+'):
            raise serializers.ValidationError(_("WhatsApp number must start with a country code (e.g., +1234567890)."))
        
        user = self.context['request'].user
        # Check if this number is already verified by *another* user
        if User.objects.filter(whatsapp_number=value, is_whatsapp_verified=True).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(_("This WhatsApp number is already verified by another account."))
        # Allow sending code to own unverified number or a new number not verified by others.
        return value


class VerifyWhatsAppSerializer(serializers.Serializer):
    whatsapp_verification_code = serializers.CharField(max_length=6, required=True)

    def validate_whatsapp_verification_code(self, value):
        user = self.context['request'].user
        if not user.whatsapp_verification_code or user.whatsapp_verification_code != value:
            raise serializers.ValidationError(_("Invalid verification code."))
        
        if user.whatsapp_code_created_at:
            expiry_duration = timezone.timedelta(minutes=getattr(settings, 'WHATSAPP_CODE_EXPIRY_MINUTES', 10))
            if timezone.now() > user.whatsapp_code_created_at + expiry_duration:
                user.whatsapp_verification_code = None # Expire the code
                user.whatsapp_code_created_at = None
                user.save(update_fields=['whatsapp_verification_code', 'whatsapp_code_created_at'])
                raise serializers.ValidationError(_("Verification code has expired. Please request a new one."))
        else: 
            raise serializers.ValidationError(_("Verification code not found or creation time missing. Please request a new one."))
            
        return value
