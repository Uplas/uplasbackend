from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView, # Standard login view
    TokenRefreshView,  # Standard refresh token view
    TokenVerifyView    # Standard token verify view
)

from .views import (
    UserRegistrationView,
    UserProfileView, # Changed from UserProfileViewSet to UserProfileView
    PasswordChangeView,
    SendWhatsAppVerificationView,
    VerifyWhatsAppView,
)

app_name = 'users'


urlpatterns = [
    # User Registration
    path('register/', UserRegistrationView.as_view(), name='user-register'),

    # JWT Authentication Endpoints
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # User Profile Management (Retrieve/Update own profile)
    path('profile/', UserProfileView.as_view(), name='user-profile-detail'),

    # Password Change
    path('profile/change-password/', PasswordChangeView.as_view(), name='change-password'),

    # WhatsApp Verification
    path('profile/whatsapp/send-code/', SendWhatsAppVerificationView.as_view(), name='whatsapp-send-code'),
    path('profile/whatsapp/verify-code/', VerifyWhatsAppView.as_view(), name='whatsapp-verify-code'),
]
