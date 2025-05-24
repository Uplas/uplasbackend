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
    # id = serializers.UUIDField(read_only=True) # Inherited from BaseModel
    # user_email = serializers.EmailField(source='user.email', read_only=True) # For context

    class Meta:
        model = UserProfile
        fields = [
            'id', 'user', # user field is read-only by default if it's the PK relation
            'bio', 'linkedin_url', 'github_url', 'website_url',
            'preferred_tutor_persona', 'preferred_tts_voice_character',
            'preferred_ttv_instructor', 'learning_style_preference',
            'areas_of_interest', 'current_knowledge_level', 'learning_goals',
            'created_at', 'updated_at' # From BaseModel
        ]
        read_only_fields = ('id', 'user', 'created_at', 'updated_at') # User should not be changed here

    def update(self, instance, validated_data):
        # Custom update logic if needed, e.g., for JSONFields
        return super().update(instance, validated_data)


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model.
    Includes nested UserProfile data for comprehensive user representation.
    Used for retrieving user details and updating them (by owner or admin).
    """
    profile = UserProfileSerializer(required=False) # Allow partial updates without profile data

    # Make choice fields display their readable values
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
            'is_premium_subscriber', # 'subscription_plan_name', 'subscription_end_date', # These might be better via payments app
            'country', 'city', 'stripe_customer_id',
            'profile', # Nested profile
            'is_staff', 'is_active', 'date_joined', 'last_login',
            'created_at', 'updated_at' # Explicitly added to User model
        ]
        read_only_fields = (
            'id', 'username', # Username typically not changed after creation, or only by admin
            'is_whatsapp_verified', 'uplas_xp_points',
            'is_premium_subscriber', # Managed by payments system
            'stripe_customer_id', # Managed by payments system
            'is_staff', 'is_active', # Typically managed by admin
            'date_joined', 'last_login', 'created_at', 'updated_at',
            'industry_display', 'preferred_language_display', 'preferred_currency_display'
        )
        extra_kwargs = {
            'email': {'required': False}, # Allow partial updates without email, but required on create
            'password': {'write_only': True, 'required': False}, # For password changes, not for general update
            'first_name': {'required': False},
            'last_name': {'required': False},
        }

    def validate_industry(self, value):
        if value == 'Other' and not self.initial_data.get('other_industry_details'):
            raise serializers.ValidationError(_("Please specify details if 'Other' industry is selected."))
        return value
    
    def validate_whatsapp_number(self, value):
        # Add more specific validation for WhatsApp number format if needed
        if value and not value.startswith('+'):
            raise serializers.ValidationError(_("WhatsApp number must start with a country code (e.g., +1234567890)."))
        # Check for uniqueness if it's being set or changed (model handles on save, but good for early feedback)
        # user = self.context['request'].user if 'request' in self.context else None
        # query = User.objects.filter(whatsapp_number=value)
        # if self.instance: # If updating
        #     query = query.exclude(pk=self.instance.pk)
        # if user and self.instance and user != self.instance and not user.is_staff: # User changing other's number
        #      raise serializers.ValidationError(_("You cannot set this WhatsApp number."))
        # if query.exists():
        #     raise serializers.ValidationError(_("This WhatsApp number is already in use."))
        return value


    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        
        # Handle password separately if provided for update
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)

        # Update User instance
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update nested UserProfile if data is provided
        if profile_data is not None:
            profile_instance = instance.profile
            if profile_instance:
                for attr, value in profile_data.items():
                    setattr(profile_instance, attr, value)
                profile_instance.save()
            # else: UserProfile.objects.create(user=instance, **profile_data) # Should be created by signal

        return instance


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password], # Django's built-in password validators
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    # Include fields from User model that are required/allowed at registration
    # username is required by AbstractUser, but we auto-generate it.
    # We can make it optional here and let the model/manager handle it.
    username = serializers.CharField(required=False, allow_blank=True, max_length=150)


    class Meta:
        model = User
        fields = (
            'email', 'username', 'password', 'password_confirm',
            'full_name', 'first_name', 'last_name', # Optional at registration
            'organization', 'industry', 'other_industry_details', 'profession',
            'preferred_language', 'preferred_currency', 'country', 'city',
            'career_interest', 'whatsapp_number' # Optional WhatsApp at registration
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
        # Username might be optional if auto-generated, but if provided, validate uniqueness
        if value and User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(_("This username is already taken. Please choose another."))
        return value
    
    def validate_whatsapp_number(self, value):
        if value: # If provided
            if not value.startswith('+'):
                raise serializers.ValidationError(_("WhatsApp number must start with a country code (e.g., +1234567890)."))
            if User.objects.filter(whatsapp_number=value).exists():
                raise serializers.ValidationError(_("This WhatsApp number is already registered."))
        return value

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({"password_confirm": _("Password fields didn't match.")})
        
        # Validate industry and other_industry_details
        industry = attrs.get('industry')
        other_industry_details = attrs.get('other_industry_details')
        if industry == 'Other' and not other_industry_details:
            raise serializers.ValidationError({
                "other_industry_details": _("Please specify details if 'Other' industry is selected.")
            })
        if industry != 'Other' and other_industry_details:
            # Optionally clear other_industry_details if industry is not 'Other'
            attrs['other_industry_details'] = None 
            # Or raise ValidationError("Other industry details should only be provided if 'Other' industry is selected.")

        attrs.pop('password_confirm') # Remove confirm password from attributes to be saved
        return attrs

    def create(self, validated_data):
        # User.objects.create_user will handle password hashing and username generation if not provided
        user = User.objects.create_user(**validated_data)
        # UserProfile is created via post_save signal on User model
        return user


class UserLoginSerializer(serializers.Serializer): # Not a ModelSerializer
    """
    Serializer for user login.
    Typically, DRF Simple JWT's TokenObtainPairSerializer is used and customized.
    This is a simpler version if you handle token generation manually or want a specific request format.
    """
    email = serializers.EmailField(label=_("Email Address"))
    password = serializers.CharField(
        label=_("Password"),
        style={'input_type': 'password'},
        trim_whitespace=False
    )

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(request=self.context.get('request'), email=email, password=password)
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

# For DRF Simple JWT, you would typically customize TokenObtainPairSerializer:
# from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
# class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
#     @classmethod
#     def get_token(cls, user):
#         token = super().get_token(user)
#         # Add custom claims
#         token['username'] = user.username
#         token['full_name'] = user.full_name
#         # ...
#         return token

#     def validate(self, attrs):
#         data = super().validate(attrs)
#         # Add user data to the response
#         data['user'] = UserSerializer(self.user, context=self.context).data
#         return data


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

    def save(self, **kwargs):
        password = self.validated_data['new_password']
        user = self.context['request'].user
        user.set_password(password)
        user.save()
        return user


class SendWhatsAppVerificationSerializer(serializers.Serializer):
    whatsapp_number = serializers.CharField(max_length=20, required=True)

    def validate_whatsapp_number(self, value):
        if not value.startswith('+'):
            raise serializers.ValidationError(_("WhatsApp number must start with a country code (e.g., +1234567890)."))
        # Check if this number is already verified by another user (optional, depends on policy)
        # if User.objects.filter(whatsapp_number=value, is_whatsapp_verified=True).exclude(pk=self.context['request'].user.pk).exists():
        #     raise serializers.ValidationError(_("This WhatsApp number is already verified by another account."))
        return value


class VerifyWhatsAppSerializer(serializers.Serializer):
    whatsapp_verification_code = serializers.CharField(max_length=6, required=True)

    def validate_whatsapp_verification_code(self, value):
        user = self.context['request'].user
        if not user.whatsapp_verification_code or user.whatsapp_verification_code != value:
            raise serializers.ValidationError(_("Invalid verification code."))
        
        # Check code expiry (e.g., 10 minutes)
        if user.whatsapp_code_created_at:
            expiry_duration = timezone.timedelta(minutes=getattr(settings, 'WHATSAPP_CODE_EXPIRY_MINUTES', 10))
            if timezone.now() > user.whatsapp_code_created_at + expiry_duration:
                raise serializers.ValidationError(_("Verification code has expired. Please request a new one."))
        else: # Should not happen if code was generated
            raise serializers.ValidationError(_("Verification code not found or creation time missing."))
            
        return value

