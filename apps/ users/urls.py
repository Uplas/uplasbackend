from django.urls import path
from .views import (
    UserRegistrationView,
    UserLoginView,
    UserProfileView,
    VerifyWhatsAppView,
    SendWhatsAppVerificationView,
)
from rest_framework_simplejwt.views import TokenRefreshView

app_name = 'users'

urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='register'), # /api/users/register/ 
    path('login/', UserLoginView.as_view(), name='login'),               # /api/users/login/ 
    path('profile/', UserProfileView.as_view(), name='profile'),         # /api/users/profile/ 
    path('verify-whatsapp/', VerifyWhatsAppView.as_view(), name='verify-whatsapp'), # /api/users/verify-whatsapp/ 
    path('send-whatsapp-code/', SendWhatsAppVerificationView.as_view(), name='send-whatsapp-code'),
    
    # JWT Token Refresh endpoint (from DRF Simple JWT)
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), # /api/token/refresh/ 
]
