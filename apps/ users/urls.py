from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserRegistrationView,
    UserLoginView,
    UserProfileViewSet, # Changed to ViewSet
    VerifyWhatsAppView,
    SendWhatsAppVerificationView,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# For UserProfileViewSet, as it's a single resource for the current user at /api/users/profile/
# We can map its actions directly without a router, or use a router and map only specific actions if preferred.
# Simpler direct mapping for a single profile resource:
profile_detail_actions = UserProfileViewSet.as_view({
    'get': 'list', # Mapped list to GET for the single profile
    'put': 'update',
    'patch': 'partial_update'
})


app_name = 'users'

urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('login/', UserLoginView.as_view(), name='login'), # Using custom login
    # path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'), # Standard SimpleJWT if custom login not preferred
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), # 
    
    path('profile/', profile_detail_actions, name='user-profile'), # For current user's profile
    
    path('whatsapp/send-code/', SendWhatsAppVerificationView.as_view(), name='whatsapp-send-code'),
    path('whatsapp/verify-code/', VerifyWhatsAppView.as_view(), name='whatsapp-verify-code'),
]
