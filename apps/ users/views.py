from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
# UserLoginSerializer was removed as the UserLoginView that used it is removed.
# SimpleJWT's TokenObtainPairView is used instead via urls.py.
# from .serializers import UserLoginSerializer
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from .serializers import (
    UserSerializer,
    UserRegistrationSerializer,
    PasswordChangeSerializer, # Added import
    SendWhatsAppVerificationSerializer, # Added import
    VerifyWhatsAppSerializer # Added import
)
from .permissions import IsAccountOwnerOrReadOnly # Assuming this is the primary permission for UserProfileView

User = get_user_model()

class UserRegistrationView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

# UserLoginView has been removed as per feedback (it was unused).
# TokenObtainPairView from SimpleJWT is used directly in urls.py.

class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for the current authenticated user's profile.
    GET to retrieve, PUT/PATCH to update.
    Accessible at /api/users/profile/
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountOwnerOrReadOnly]

    def get_object(self):
        # IsAccountOwnerOrReadOnly permission will ensure only owner or admin can PUT/PATCH.
        # For GET, IsAuthenticated is enough.
        return self.request.user

    def get_queryset(self):
        # Although get_object is used, providing a queryset is good practice for ViewSet.
        # For retrieve/update of a single user profile, this helps with potential pre-fetching if UserSerializer becomes more complex.
        return User.objects.select_related('profile').filter(pk=self.request.user.pk)


class PasswordChangeView(generics.UpdateAPIView):
    """
    An endpoint for changing password.
    """
    serializer_class = PasswordChangeSerializer
    model = User
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self, queryset=None):
        return self.request.user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Check old password
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": [_("Wrong password.")]}, status=status.HTTP_400_BAD_REQUEST)
            # set_password also hashes the password that the user will get
            self.object.set_password(serializer.data.get("new_password"))
            self.object.save()
            return Response({"detail": _("Password updated successfully.")}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SendWhatsAppVerificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SendWhatsAppVerificationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        new_whatsapp_number = serializer.validated_data['whatsapp_number']

        # Check if this number is already verified by another user
        if User.objects.filter(whatsapp_number=new_whatsapp_number, is_whatsapp_verified=True).exclude(pk=user.pk).exists():
            return Response({'error': _('This WhatsApp number is already verified by another account.')}, status=status.HTTP_400_BAD_REQUEST)

        user.whatsapp_number = new_whatsapp_number # Update user's number
        
        # Prevent rapid re-requests for code generation
        if user.whatsapp_code_created_at and timezone.now() < user.whatsapp_code_created_at + timedelta(minutes=1): # 1 minute cooldown
             return Response({'detail': _('Verification code recently sent. Please wait before requesting a new one.')}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        code = user.generate_whatsapp_code() # This method now saves the user instance with the new code and timestamp

        # TODO: Integrate with a real WhatsApp API provider (e.g., Twilio, Vonage, Meta API)
        print(f"SIMULATED: Sent WhatsApp verification code {code} to {user.whatsapp_number} for user {user.email}")
        # In a real scenario:
        # success = send_whatsapp_message_via_api(user.whatsapp_number, f"Your Uplas verification code is: {code}")
        # if not success:
        #     return Response({'detail': 'Failed to send verification code. Please try again later.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'detail': _('Verification code sent to your WhatsApp number.'),
            'whatsapp_number': user.whatsapp_number # Return the number it was sent to
            }, status=status.HTTP_200_OK)


class VerifyWhatsAppView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VerifyWhatsAppSerializer

    def post(self, request, *args, **kwargs):
        user = request.user
        # Pass context to serializer if it needs the request/user
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Serializer validation already checks code validity and expiry
        
        user.is_whatsapp_verified = True
        user.whatsapp_verification_code = None # Clear code after successful verification
        # whatsapp_code_created_at is not cleared here, but new codes will overwrite it.
        user.save(update_fields=['is_whatsapp_verified', 'whatsapp_verification_code'])
        
        return Response({'detail': _('WhatsApp number verified successfully.')}, status=status.HTTP_200_OK)
