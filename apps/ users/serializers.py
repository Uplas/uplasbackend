from rest_framework import serializers
from .models import User, UserProfile, INDUSTRY_CHOICES, LANGUAGE_CHOICES, CURRENCY_CHOICES
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            'bio', 'linkedin_url', 'github_url', 'website_url',
            'preferred_tutor_persona', 'preferred_tts_voice', 'preferred_ttv_instructor',
            'learning_style_preference', 'areas_of_interest', 'current_knowledge_level', 'learning_goals'
        ]
        # All fields are optional for update

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(required=False) # Nested serializer for profile data

    # Make choices human-readable in API responses
    industry_display = serializers.CharField(source='get_industry_display', read_only=True)
    preferred_language_display = serializers.CharField(source='get_preferred_language_display', read_only=True)
    preferred_currency_display = serializers.CharField(source='get_preferred_currency_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name',
            'organization', 'industry', 'industry_display', 'other_industry_details', 'profession',
            'whatsapp_number', 'is_whatsapp_verified',
            'preferred_language', 'preferred_language_display',
            'preferred_currency', 'preferred_currency_display',
            'profile_picture_url', 'career_interest',
            'uplas_xp_points', 'is_premium_subscriber', 'subscription_plan', 'subscription_end_date',
            'country', 'city',
            'profile' # Include the nested profile
        ]
        read_only_fields = ['id', 'username', 'uplas_xp_points', 'is_whatsapp_verified', 'is_premium_subscriber', 'subscription_plan', 'subscription_end_date']
        extra_kwargs = {
            'email': {'required': True, 'allow_blank': False},
            'full_name': {'required': False, 'allow_blank': True},
            # Add other required fields for update if necessary
        }

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        
        # Update User fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update UserProfile fields
        if profile_data is not None:
            profile_instance = instance.profile
            for attr, value in profile_data.items():
                setattr(profile_instance, attr, value)
            profile_instance.save()
            
        return instance

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    industry = serializers.ChoiceField(choices=INDUSTRY_CHOICES, required=True)
    # Explicitly declare other required fields from the frontend guide
    full_name = serializers.CharField(required=True)
    profession = serializers.CharField(required=True)
    whatsapp_number = serializers.CharField(required=True) # Basic validation, consider phonenumbers library for more robust
    
    class Meta:
        model = User
        fields = (
            'username', # Will be auto-generated or use email
            'email',
            'full_name',
            'password',
            'password_confirm',
            'organization',
            'industry',
            'other_industry_details',
            'profession',
            'whatsapp_number',
            'preferred_language', # Optional on signup, defaults can be used
            'preferred_currency', # Optional on signup
            'career_interest',    # Optional on signup
            'country',            # Optional, can be derived via IP or asked later
            'city'                # Optional
        )
        extra_kwargs = {
            'organization': {'required': False, 'allow_blank': True},
            'other_industry_details': {'required': False, 'allow_blank': True},
            'preferred_language': {'required': False},
            'preferred_currency': {'required': False},
            'career_interest': {'required': False},
        }

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(_("A user with this email already exists."))
        return value

    def validate_whatsapp_number(self, value):
        # Add more robust validation if needed (e.g., using phonenumbers library)
        if User.objects.filter(whatsapp_number=value).exists():
            raise serializers.ValidationError(_("This WhatsApp number is already registered."))
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": _("Password fields didn't match.")})
        
        if attrs.get('industry') == 'Other' and not attrs.get('other_industry_details'):
            raise serializers.ValidationError({"other_industry_details": _("Please specify your industry if 'Other' is selected.")})
        elif attrs.get('industry') != 'Other': # Clear other_industry_details if not 'Other'
            attrs['other_industry_details'] = None

        # Auto-generate username from email if not provided or keep it simple for now
        if 'username' not in attrs or not attrs['username']:
            attrs['username'] = attrs['email'].split('@')[0] + str(random.randint(1000,9999)) 
            # Ensure username uniqueness if auto-generating
            while User.objects.filter(username=attrs['username']).exists():
                attrs['username'] = attrs['email'].split('@')[0] + str(random.randint(1000,9999))
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        # Extract profile related data if any was part of the signup directly
        # For now, profile is created/updated via signals
        
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            full_name=validated_data.get('full_name', ''),
            organization=validated_data.get('organization', ''),
            industry=validated_data.get('industry'),
            other_industry_details=validated_data.get('other_industry_details', ''),
            profession=validated_data.get('profession', ''),
            whatsapp_number=validated_data.get('whatsapp_number'),
            preferred_language=validated_data.get('preferred_language', settings.LANGUAGE_CODE),
            preferred_currency=validated_data.get('preferred_currency', 'USD'),
            career_interest=validated_data.get('career_interest', ''),
            country=validated_data.get('country',''),
            city=validated_data.get('city','')
        )
        # UserProfile is created by the post_save signal
        return user

class WhatsAppVerificationSerializer(serializers.Serializer):
    code = serializers.CharField(required=True, max_length=6, min_length=6)

    def validate_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError(_("Verification code must be numeric."))
        return value
