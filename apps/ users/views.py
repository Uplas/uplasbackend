from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model # Use get_user_model()
from django.shortcuts import get_object_or_404


from .serializers import (
    UserSerializer, UserRegistrationSerializer, UserLoginSerializer,
    UserProfileSerializer, WhatsAppVerificationSerializer
)
# from .permissions import IsOwnerOrAdminOrReadOnly # If you create custom permissions

User = get_user_model()

class UserRegistrationView(generics.CreateAPIView): # POST /api/users/register/ 
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    # perform_create is handled by serializer's create method

class UserLoginView(APIView): # POST /api/users/login/ 
    permission_classes = [permissions.AllowAny]
    serializer_class = UserLoginSerializer # Use the serializer for validation

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        
        refresh = RefreshToken.for_user(user)
        user_data = UserSerializer(user, context={'request': request}).data

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': user_data
        })

class UserProfileViewSet(viewsets.ModelViewSet): # Replaces UserProfileView for more standard GET/PUT/PATCH
    """
    API endpoint for the current authenticated user's profile.
    GET, PUT, PATCH /api/users/profile/  (Implicitly for current user)
    
    """
    serializer_class = UserSerializer # Uses UserSerializer which includes UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Returns the currently authenticated user
        return self.request.user
    
    def get_queryset(self): # Required for base ModelViewSet, even if get_object is overridden for detail views
        return User.objects.filter(pk=self.request.user.pk)

    # Standard ModelViewSet actions (retrieve, update, partial_update) will work.
    # List and Destroy are typically not wanted for a '/profile/' endpoint referring to self.
    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.request.user).data)

    def destroy(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    # If you wanted a separate /api/users/{id}/ endpoint for admins, you'd create another ViewSet.

class SendWhatsAppVerificationView(APIView): # POST /api/users/send-whatsapp-code/ 
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        if not user.whatsapp_number:
            return Response({'detail': _('Please add your WhatsApp number in your profile first.')}, status=status.HTTP_400_BAD_REQUEST)
        
        if user.is_whatsapp_verified:
            return Response({'detail': _('Your WhatsApp number is already verified.')}, status=status.HTTP_400_BAD_REQUEST)

        if user.whatsapp_code_created_at and timezone.now() < user.whatsapp_code_created_at + timedelta(minutes=2):
             return Response({'detail': _('Verification code recently sent. Please wait before requesting a new one.')}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        code = user.generate_whatsapp_code()
        
        # TODO: Integrate with a real WhatsApp API provider (e.g., Twilio, Vonage, Meta API)
        # Placeholder for sending logic:
        print(f"SIMULATED: Sent WhatsApp verification code {code} to {user.whatsapp_number} for user {user.email}")
        # In a real scenario:
        # success = send_whatsapp_message_via_api(user.whatsapp_number, f"Your Uplas verification code is: {code}")
        # if not success:
        #     return Response({'detail': 'Failed to send verification code. Please try again later.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'detail': _('Verification code sent to your WhatsApp number.')}, status=status.HTTP_200_OK)

class VerifyWhatsAppView(APIView): # POST /api/users/verify-whatsapp/ 
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WhatsAppVerificationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        provided_code = serializer.validated_data['code']

        if user.is_whatsapp_verified:
            return Response({'detail': _('WhatsApp number already verified.')}, status=status.HTTP_400_BAD_REQUEST)

        if not user.whatsapp_verification_code or not user.whatsapp_code_created_at:
            return Response({'detail': _('No verification code was found for your account. Please request one first.')}, status=status.HTTP_400_BAD_REQUEST)

        if timezone.now() > user.whatsapp_code_created_at + timedelta(minutes=10): # Code expiry
            user.whatsapp_verification_code = None
            user.whatsapp_code_created_at = None
            user.save(update_fields=['whatsapp_verification_code', 'whatsapp_code_created_at'])
            return Response({'detail': _('Verification code has expired. Please request a new one.')}, status=status.HTTP_400_BAD_REQUEST)

        if user.whatsapp_verification_code == provided_code:
            user.is_whatsapp_verified = True
            user.whatsapp_verification_code = None 
            user.whatsapp_code_created_at = None
            user.save(update_fields=['is_whatsapp_verified', 'whatsapp_verification_code', 'whatsapp_code_created_at'])
            return Response({'detail': _('WhatsApp number verified successfully.')}, status=status.HTTP_200_OK)
        else:
            # TODO: Implement attempt counter to prevent brute-force if desired
            return Response({'detail': _('Invalid verification code.')}, status=status.HTTP_400_BAD_REQUEST)
