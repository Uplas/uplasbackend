from rest_framework import serializers
from .models import User, UserProfile, INDUSTRY_CHOICES, LANGUAGE_CHOICES, CURRENCY_CHOICES
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
import random

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            'bio', 'linkedin_url', 'github_url', 'website_url',
            'preferred_tutor_persona', 'preferred_tts_voice_character', 'preferred_ttv_instructor',
            'learning_style_preference', 'areas_of_interest', 'current_knowledge_level', 'learning_goals'
        ]

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(required=False, read_only=False)
    industry_display = serializers.CharField(source='get_industry_display', read_only=True)
    preferred_language_display = serializers.CharField(source='get_preferred_language_display', read_only=True)
    preferred_currency_display = serializers.CharField(source='get_preferred_currency_display', read_only=True)


    class Meta:
        model = User
        fields = [
            'id', 'username',
            'email', 'full_name', 'first_name', 'last_name',
            'organization', 'industry', 'industry_display', 'other_industry_details', 'profession',
            'whatsapp_number', 'is_whatsapp_verified',
            'preferred_language', 'preferred_language_display',
            'preferred_currency', 'preferred_currency_display',
            'profile_picture_url', 'career_interest',
            'uplas_xp_points', 'is_premium_subscriber', 'subscription_plan_name', 'subscription_end_date',
            'country', 'city',
            'stripe_customer_id',
            'profile'
        ]
        read_only_fields = [
            'id', 'username', 'uplas_xp_points', 'is_whatsapp_verified', 'is_premium_subscriber',
            'subscription_plan_name', 'subscription_end_date', 'stripe_customer_id',
            'industry_display', 'preferred_language_display', 'preferred_currency_display'
        ]
        extra_kwargs = {
            'email': {'required': False}, # Email is login, not typically changed via general profile update
            'full_name': {'required': False},
            'first_name': {'required': False},
            'last_name': {'required': False},
        }

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
            
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if not instance.full_name and (validated_data.get('first_name') or validated_data.get('last_name') or instance.first_name or instance.last_name):
            instance.full_name = f"{validated_data.get('first_name', instance.first_name) or ''} {validated_data.get('last_name', instance.last_name) or ''}".strip()
        
        instance.save()

        if profile_data is not None:
            # Ensure profile exists, especially if it might not have been created by signal yet
            # or if this is the first time profile data is being set.
            profile_instance, created = UserProfile.objects.get_or_create(user=instance)
            for attr, value in profile_data.items():
                setattr(profile_instance, attr, value)
            profile_instance.save()
            
        return instance

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password], style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    email = serializers.EmailField(required=True)
    full_name = serializers.CharField(required=True)
    profession = serializers.CharField(required=True)
    industry = serializers.ChoiceField(choices=INDUSTRY_CHOICES, required=True)
    whatsapp_number = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=20)


    class Meta:
        model = User
        fields = (
            'email', 'username', 
            'full_name',
            'password', 'password_confirm',
            'organization', 'industry', 'other_industry_details', 'profession',
            'whatsapp_number', 'preferred_language', 'preferred_currency',
            'career_interest', 'country', 'city',
        )
        extra_kwargs = {
            'username': {'read_only': True},
            'organization': {'required': False, 'allow_blank': True, 'allow_null': True},
            'other_industry_details': {'required': False, 'allow_blank': True, 'allow_null': True},
            'preferred_language': {'required': False},
            'preferred_currency': {'required': False},
            'career_interest': {'required': False, 'allow_blank': True, 'allow_null': True},
            'country': {'required': False, 'allow_blank': True, 'allow_null': True},
            'city': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(_("A user with this email already exists."))
        return value
    
    def validate_whatsapp_number(self, value):
        if value and User.objects.filter(whatsapp_number=value).exists():
            # Consider if this validation should be here or if a user can add an existing number later and verify
            # For registration, if unique, this is fine.
            raise serializers.ValidationError(_("This WhatsApp number is already registered."))
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": _("Password fields didn't match.")})
        
        if attrs.get('industry') == 'Other' and not attrs.get('other_industry_details'):
            raise serializers.ValidationError({"other_industry_details": _("Please specify your industry if 'Other' is selected.")})
        elif attrs.get('industry') != 'Other' and attrs.get('other_industry_details'): # Clear if not 'Other'
            attrs['other_industry_details'] = None
            
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        
        email_prefix = validated_data['email'].split('@')[0].replace('.', '_').replace('-', '_') # Sanitize a bit
        username_candidate = email_prefix
        counter = 0
        while User.objects.filter(username=username_candidate).exists():
            counter += 1
            username_candidate = f"{email_prefix}{counter}"
        validated_data['username'] = username_candidate

        # Ensure optional fields that are blank are passed as None if model field is nullable
        for field in ['organization', 'other_industry_details', 'whatsapp_number', 'career_interest', 'country', 'city']:
            if field in validated_data and validated_data[field] == '':
                validated_data[field] = None
        
        user = User.objects.create_user(**validated_data)
        return user

class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(request=self.context.get('request'), username=email, password=password)
            
            if not user:
                msg = _('Unable to log in with provided credentials.')
                raise serializers.ValidationError(msg, code='authorization')
            
            if not user.is_active:
                msg = _('User account is disabled.')
                raise serializers.ValidationError(msg, code='authorization')
        else:
            msg = _('Must include "email" and "password".')
            raise serializers.ValidationError(msg, code='authorization')

        attrs['user'] = user
        return attrs

class WhatsAppVerificationSerializer(serializers.Serializer):
    code = serializers.CharField(required=True, max_length=6, min_length=6)

    def validate_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError(_("Verification code must be numeric."))
        return value
