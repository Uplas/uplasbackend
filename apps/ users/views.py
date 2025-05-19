from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta


from .models import User
from .serializers import UserSerializer, UserRegistrationSerializer, WhatsAppVerificationSerializer

class UserRegistrationView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny] # Anyone can register

    def perform_create(self, serializer):
        user = serializer.save()
        # Optionally: Send welcome email or initiate WhatsApp verification code sending here
        # For WhatsApp, it's better to do it after successful registration
        # user.generate_whatsapp_code()
        # send_whatsapp_verification_code(user.whatsapp_number, user.whatsapp_verification_code)
        # print(f"Sent verification code {user.whatsapp_verification_code} to {user.whatsapp_number}")


class UserLoginView(APIView): # Matched /api/users/login/ from frontend guide 
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        password = request.data.get('password')
        if not email or not password:
            return Response({'detail': 'Email and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email=email).first()

        if user and user.check_password(password):
            if not user.is_active:
                return Response({'detail': 'User account is inactive.'}, status=status.HTTP_400_BAD_REQUEST)
            
            # For simplicity, using Simple JWT's RefreshToken directly
            refresh = RefreshToken.for_user(user)
            user_data = UserSerializer(user).data # Get serialized user data

            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': user_data # Send user data along with tokens 
            })
        return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

class UserProfileView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated] # Only authenticated users can access/update

    def get_object(self):
        # Returns the currently authenticated user's profile
        return self.request.user
    
    def partial_update(self, request, *args, **kwargs):
        # Ensure profile picture URL update is handled if that's the field name
        # If using ImageField, handling file uploads would be different.
        return super().partial_update(request, *args, **kwargs)


class SendWhatsAppVerificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        if not user.whatsapp_number:
            return Response({'detail': 'WhatsApp number not set for this user.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Basic rate limiting: Allow sending code once every X minutes (e.g., 2 minutes)
        if user.whatsapp_code_created_at and timezone.now() < user.whatsapp_code_created_at + timedelta(minutes=2):
             return Response({'detail': 'Verification code already sent. Please wait before requesting a new one.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        code = user.generate_whatsapp_code()
        
        # TODO: Integrate with a WhatsApp API provider (e.g., Twilio, Vonage, Meta's WhatsApp Business API)
        # Example placeholder for sending logic:
        # from some_whatsapp_service import send_message
        # success = send_message(user.whatsapp_number, f"Your Uplas verification code is: {code}")
        # if not success:
        #     return Response({'detail': 'Failed to send verification code. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        print(f"SIMULATED: Sent WhatsApp verification code {code} to {user.whatsapp_number}") # For development
        
        return Response({'detail': 'Verification code sent to your WhatsApp number.'}, status=status.HTTP_200_OK)


class VerifyWhatsAppView(APIView): # Matched /api/users/verify-whatsapp/ from frontend guide 
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WhatsAppVerificationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        provided_code = serializer.validated_data['code']

        if not user.whatsapp_verification_code or not user.whatsapp_code_created_at:
            return Response({'detail': 'No verification code was sent. Please request one first.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if code has expired (e.g., 10 minutes validity)
        if timezone.now() > user.whatsapp_code_created_at + timedelta(minutes=10):
            return Response({'detail': 'Verification code has expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)

        if user.whatsapp_verification_code == provided_code:
            user.is_whatsapp_verified = True
            user.whatsapp_verification_code = None # Clear code after successful verification
            user.whatsapp_code_created_at = None
            user.save()
            return Response({'detail': 'WhatsApp number verified successfully.'}, status=status.HTTP_200_OK)
        else:
            return Response({'detail': 'Invalid verification code.'}, status=status.HTTP_400_BAD_REQUEST)
