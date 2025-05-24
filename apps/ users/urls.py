from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView, # Standard login view
    TokenRefreshView,  # Standard refresh token view
    TokenVerifyView    # Standard token verify view
)

from .views import (
    UserRegistrationView,
    UserProfileView,
    PasswordChangeView,
    SendWhatsAppVerificationView,
    VerifyWhatsAppView,
    # MyTokenObtainPairView, # If you created and prefer to use your custom token view
    # AdminUserViewSet # If you implement this for admin user management
)

app_name = 'users'

# If you have an AdminUserViewSet, you would register it with a router:
# router = DefaultRouter()
# router.register(r'manage', AdminUserViewSet, basename='admin-user')

urlpatterns = [
    # User Registration
    path('register/', UserRegistrationView.as_view(), name='user-register'),

    # JWT Authentication Endpoints (Login, Refresh, Verify Token)
    # You can use the standard TokenObtainPairView or your customized MyTokenObtainPairView
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    # path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'), # If using custom
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # User Profile Management (Retrieve/Update own profile)
    # The URL /profile/ implies the currently authenticated user.
    path('profile/', UserProfileView.as_view(), name='user-profile-detail'), # GET to retrieve, PUT/PATCH to update

    # Password Change
    path('profile/change-password/', PasswordChangeView.as_view(), name='change-password'),

    # WhatsApp Verification
    path('profile/whatsapp/send-code/', SendWhatsAppVerificationView.as_view(), name='whatsapp-send-code'),
    path('profile/whatsapp/verify-code/', VerifyWhatsAppView.as_view(), name='whatsapp-verify-code'),

    # Include router URLs if you have ViewSets like AdminUserViewSet
    # path('admin/', include(router.urls)), # Example if AdminUserViewSet is at /admin/manage/
]

# --- Example Generated URLs (assuming base path /api/users/) ---
# /api/users/register/ (POST)
# /api/users/login/ (POST)
# /api/users/token/refresh/ (POST)
# /api/users/token/verify/ (POST)
# /api/users/profile/ (GET, PUT, PATCH)
# /api/users/profile/change-password/ (PUT or PATCH)
# /api/users/profile/whatsapp/send-code/ (POST)
# /api/users/profile/whatsapp/verify-code/ (POST)
#
# If AdminUserViewSet was added and registered to 'admin/manage/':
# /api/users/admin/manage/ (GET list, POST create)
# /api/users/admin/manage/{user_id}/ (GET retrieve, PUT/PATCH update, DELETE)

