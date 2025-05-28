from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta # Correct import for timedelta
from django.conf import settings # For WHATSAPP_CODE_EXPIRY_MINUTES

from .serializers import (
    UserSerializer,
    UserRegistrationSerializer,
    PasswordChangeSerializer,
    SendWhatsAppVerificationSerializer,
    VerifyWhatsAppSerializer
)
from .permissions import IsAccountOwnerOrReadOnly 

User = get_user_model()

class UserRegistrationView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny] # Anyone can register

    def perform_create(self, serializer):
        # The serializer's create method handles user creation and password hashing.
        # It also generates a username if not provided.
        user = serializer.save()
        # UserProfile is created via post_save signal on User model.
        # Optionally, send a welcome email or perform other post-registration actions here.


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for the current authenticated user to retrieve or update their profile.
    GET to retrieve, PUT/PATCH to update.
    Accessible at /api/users/profile/
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountOwnerOrReadOnly]

    def get_object(self):
        # IsAccountOwnerOrReadOnly permission will ensure only owner or admin can PUT/PATCH.
        # For GET, IsAuthenticated is enough.
        # The permission class handles checking if request.user is the object owner.
        return self.request.user

    def get_queryset(self):
        # This queryset is used by get_object if lookup_field is involved,
        # but since get_object is overridden, it's more for DRF's internal workings.
        # For retrieve/update of a single user profile (self.request.user).
        return User.objects.select_related('profile').filter(pk=self.request.user.pk)


class PasswordChangeView(generics.GenericAPIView): # Changed from UpdateAPIView for more control
    """
    An endpoint for changing password.
    """
    serializer_class = PasswordChangeSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def post(self, request, *args, **kwargs): # Changed to POST as it's an action
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Serializer's validate_old_password and validate methods handle checks.
            serializer.save() # Serializer's save method sets the new password
            return Response({"detail": _("Password updated successfully.")}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SendWhatsAppVerificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SendWhatsAppVerificationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        new_whatsapp_number = serializer.validated_data['whatsapp_number']

        # Prevent rapid re-requests for code generation
        # Using settings.WHATSAPP_CODE_EXPIRY_MINUTES for cooldown is too long, use a shorter fixed duration like 1 minute
        cooldown_minutes = 1 
        if user.whatsapp_code_created_at and timezone.now() < user.whatsapp_code_created_at + timedelta(minutes=cooldown_minutes):
             return Response({'detail': _(f'Verification code recently sent. Please wait {cooldown_minutes} minute(s) before requesting a new one.')}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # Update user's number before sending code.
        # This ensures the code is associated with the number they are trying to verify.
        user.whatsapp_number = new_whatsapp_number
        # is_whatsapp_verified will be set to False if the number changes or is new,
        # until it's verified. This should ideally be handled in User.save() or by a signal
        # if whatsapp_number changes. For now, we ensure it's False for a new verification attempt.
        user.is_whatsapp_verified = False 
        user.save(update_fields=['whatsapp_number', 'is_whatsapp_verified'])

        code = user.generate_whatsapp_code() # This method now saves the user instance

        # TODO: Integrate with a real WhatsApp API provider (e.g., Twilio, Vonage, Meta API)
        print(f"SIMULATED: Sent WhatsApp verification code {code} to {user.whatsapp_number} for user {user.email}")
        # In a real scenario:
        # success = send_whatsapp_message_via_api(user.whatsapp_number, f"Your Uplas verification code is: {code}")
        # if not success:
        #     return Response({'detail': 'Failed to send verification code. Please try again later.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'detail': _('Verification code sent to your WhatsApp number.'),
            'whatsapp_number': user.whatsapp_number 
            }, status=status.HTTP_200_OK)


class VerifyWhatsAppView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VerifyWhatsAppSerializer

    def post(self, request, *args, **kwargs):
        user = request.user
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Serializer validation already checks code validity and expiry
        
        # Ensure the number being verified is the one stored on the user (which was set in SendWhatsAppVerificationView)
        # This step is implicitly handled as the code is tied to user.whatsapp_verification_code.

        user.is_whatsapp_verified = True
        user.whatsapp_verification_code = None # Clear code after successful verification
        user.whatsapp_code_created_at = None # Clear creation time as well
        user.save(update_fields=['is_whatsapp_verified', 'whatsapp_verification_code', 'whatsapp_code_created_at', 'updated_at'])
        
        return Response({'detail': _('WhatsApp number verified successfully.')}, status=status.HTTP_200_OK)
