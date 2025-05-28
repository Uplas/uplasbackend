from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

from .serializers import (
    UserSerializer,
    UserRegistrationSerializer,
    PasswordChangeSerializer,
    SendWhatsAppVerificationSerializer,
    VerifyWhatsAppSerializer,
    UserProfileSerializer # Ensure UserProfileSerializer is imported if used
)
from .models import UserProfile
from .permissions import IsAccountOwnerOrReadOnly

User = get_user_model()


class UserRegistrationView(generics.CreateAPIView):
    """
    API view for user registration.
    Allows any user to create a new account.
    """
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        """
        Hashes the password and saves the user upon creation.
        """
        user = serializer.save()
        # You might want to send a welcome email or perform other actions here


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    API view for retrieving and updating the authenticated user's profile.
    Uses UserSerializer which includes nested UserProfileSerializer.
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountOwnerOrReadOnly]

    def get_object(self):
        """
        Returns the currently authenticated user.
        """
        return self.request.user

    def get_queryset(self):
        """
        Returns a queryset containing only the authenticated user,
        optimized with select_related for the profile.
        """
        return User.objects.select_related('profile').filter(pk=self.request.user.pk)


class PasswordChangeView(generics.UpdateAPIView):
    """
    API view for changing the user's password.
    Requires the user to be authenticated.
    """
    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """
        Returns the currently authenticated user.
        """
        return self.request.user

    def update(self, request, *args, **kwargs):
        """
        Handles the password change process.
        """
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response({'detail': _('Password updated successfully.')}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SendWhatsAppVerificationView(APIView):
    """
    API view to send a WhatsApp verification code to the user's number.
    Includes a cooldown period to prevent abuse.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SendWhatsAppVerificationSerializer

    def post(self, request, *args, **kwargs):
        """
        Handles the request to send the verification code.
        """
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        new_whatsapp_number = serializer.validated_data['whatsapp_number']

        cooldown_minutes = getattr(settings, 'WHATSAPP_RESEND_COOLDOWN_MINUTES', 1)
        if user.whatsapp_code_created_at and \
           timezone.now() < user.whatsapp_code_created_at + timedelta(minutes=cooldown_minutes):
            return Response(
                {'detail': _(f'Please wait {cooldown_minutes} minute(s) before requesting a new code.')},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Update user's number and reset verification status before sending code
        user.whatsapp_number = new_whatsapp_number
        user.is_whatsapp_verified = False
        user.save(update_fields=['whatsapp_number', 'is_whatsapp_verified', 'updated_at'])
        code = user.generate_whatsapp_code() # This saves code and timestamp

        # --- TODO: Implement Actual WhatsApp Sending Logic Here ---
        # Use a service like Twilio or another provider.
        # Example (Simulation):
        print(f"DEBUG: Sending WhatsApp code {code} to {user.whatsapp_number} for {user.email}")
        # In a real scenario, handle potential errors from the sending service.
        # --- End TODO ---

        return Response({
            'detail': _('Verification code sent successfully.'),
            'whatsapp_number': user.whatsapp_number
        }, status=status.HTTP_200_OK)


class VerifyWhatsAppView(APIView):
    """
    API view to verify the WhatsApp code entered by the user.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VerifyWhatsAppSerializer

    def post(self, request, *args, **kwargs):
        """
        Handles the code verification request.
        """
        user = request.user
        serializer = self.serializer_class(data=request.data, context={'request': request})

        if serializer.is_valid():
            user.is_whatsapp_verified = True
            user.whatsapp_verification_code = None # Clear code after verification
            user.whatsapp_code_created_at = None
            user.save(update_fields=['is_whatsapp_verified', 'whatsapp_verification_code', 'whatsapp_code_created_at', 'updated_at'])
            return Response({'detail': _('WhatsApp number verified successfully.')}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
