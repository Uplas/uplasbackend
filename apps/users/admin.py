from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

# Import your custom User model and UserProfile model
from .models import User, UserProfile

# --- Inline Admin for UserProfile ---
class UserProfileInline(admin.StackedInline): # Or admin.TabularInline for a more compact view
    """
    Inline admin descriptor for UserProfile.
    This allows editing UserProfile fields directly within the User admin page.
    """
    model = UserProfile
    can_delete = False # Usually, a UserProfile is deleted when the User is deleted
    verbose_name_plural = _('Profile')
    fk_name = 'user' # Explicitly state the foreign key if not 'user' (though it is here)
    
    # Define which fields from UserProfile to show inline
    # You can use fieldsets here too for better organization if many fields
    fields = (
        'bio', 'linkedin_url', 'github_url', 'website_url',
        'preferred_tutor_persona', 'preferred_tts_voice_character',
        'preferred_ttv_instructor', 'learning_style_preference',
        'areas_of_interest', 'current_knowledge_level', 'learning_goals'
    )
    # If some fields are JSON and hard to edit inline, consider making them readonly
    # or providing custom widgets if needed, or just linking to a separate UserProfile admin.
    # readonly_fields = ('learning_style_preference', 'areas_of_interest', 'current_knowledge_level') # Example

# --- Custom UserAdmin ---
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Admin configuration for the custom User model.
    Extends Django's base UserAdmin.
    """
    # Add UserProfile inline
    inlines = (UserProfileInline,)

    # List display in the admin change list
    list_display = (
        'email', 'username', 'full_name', 'is_staff', 'is_active',
        'is_whatsapp_verified', 'is_premium_subscriber', 'date_joined', 'last_login'
    )
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'is_premium_subscriber', 'date_joined', 'last_login', 'industry')
    search_fields = ('email', 'username', 'full_name', 'profile__bio') # Can search through related profile fields

    # Fields to display in the User change form (add/edit view)
    # Start with base UserAdmin fieldsets and add custom ones
    # Ordering matters here.
    
    # Take existing fieldsets from BaseUserAdmin
    # BaseUserAdmin.fieldsets is:
    # (None, {'fields': ('username', 'password')}),
    # (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
    # (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    # (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    
    # Define new fieldsets by extending or replacing
    fieldsets = (
        (None, {'fields': ('email', 'password')}), # Email is now primary, username is secondary but still present
        (_('User Identifiers'), {'fields': ('username',)}), # Keep username accessible
        (_('Personal info'), {'fields': ('full_name', 'first_name', 'last_name', 'organization', 'industry', 'other_industry_details', 'profession', 'profile_picture_url')}),
        (_('Contact & Preferences'), {'fields': (
            'whatsapp_number', 'is_whatsapp_verified', # 'whatsapp_verification_code', 'whatsapp_code_created_at', # Usually not directly edited by admin
            'preferred_language', 'preferred_currency'
        )}),
        (_('Platform Specific'), {'fields': ('career_interest', 'uplas_xp_points')}),
        (_('Subscription & Financial'), {'fields': ('is_premium_subscriber', 'stripe_customer_id')}), # Denormalized sub info better as readonly if managed by payments
        (_('Location'), {'fields': ('country', 'city')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined', 'created_at', 'updated_at')}),
    )
    
    # Add custom fields to the add form as well
    # BaseUserAdmin.add_fieldsets is:
    # (None, {
    #     'classes': ('wide',),
    #     'fields': ('username', 'email', 'password', 'password2'), # We use email as USERNAME_FIELD
    # }),
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password', 'password2'), # 'password2' for confirmation
        }),
        (_('Personal info (Optional on create)'), {
            'classes': ('wide',),
            'fields': ('full_name', 'first_name', 'last_name', 'organization', 'industry', 'other_industry_details', 'profession')
        }),
        # Add other fields that can be set at creation by admin if needed
    )

    readonly_fields = ('last_login', 'date_joined', 'created_at', 'updated_at', 'uplas_xp_points') # Add fields that shouldn't be manually edited
    ordering = ('-date_joined', 'email') # Default ordering in admin list

    # If you are using a custom form for adding users (e.g., CustomUserCreationForm)
    # add_form = YourCustomUserCreationForm
    # If you are using a custom form for changing users (e.g., CustomUserChangeForm)
    # form = YourCustomUserChangeForm

    # Action to verify WhatsApp for selected users (example)
    def mark_whatsapp_verified(self, request, queryset):
        queryset.update(is_whatsapp_verified=True)
    mark_whatsapp_verified.short_description = _("Mark selected users' WhatsApp as verified")

    # Action to make selected users premium (example, ideally handled by payments)
    def make_premium(self, request, queryset):
        queryset.update(is_premium_subscriber=True) # Add subscription_end_date logic if needed
    make_premium.short_description = _("Mark selected users as premium subscribers")

    actions = [mark_whatsapp_verified, make_premium]


# If UserProfile should also be manageable separately (though inline is often enough)
# @admin.register(UserProfile)
# class UserProfileAdmin(admin.ModelAdmin):
#     list_display = ('user_email', 'bio_summary', 'linkedin_url', 'github_url', 'updated_at')
#     search_fields = ('user__email', 'user__username', 'bio', 'linkedin_url', 'github_url')
#     list_filter = ('updated_at', 'preferred_tutor_persona', 'preferred_ttv_instructor')
#     readonly_fields = ('id', 'user', 'created_at', 'updated_at') # user link is crucial
#     autocomplete_fields = ['user'] # For easier linking if creating standalone

#     fieldsets = (
#         (None, {'fields': ('user', 'bio')}),
#         (_('Professional Links'), {'fields': ('linkedin_url', 'github_url', 'website_url')}),
#         (_('AI Personalization'), {'fields': (
#             'preferred_tutor_persona', 'preferred_tts_voice_character',
#             'preferred_ttv_instructor', 'learning_style_preference',
#             'areas_of_interest', 'current_knowledge_level', 'learning_goals'
#         )}),
#         (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
#     )

#     def user_email(self, obj):
#         return obj.user.email
#     user_email.short_description = _('User Email')

#     def bio_summary(self, obj):
#         if obj.bio:
#             return (obj.bio[:75] + '...') if len(obj.bio) > 75 else obj.bio
#         return "-"
#     bio_summary.short_description = _('Bio Summary')


