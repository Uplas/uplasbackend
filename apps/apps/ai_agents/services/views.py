# uplas-backend/apps/ai_agents/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .serializers import (
    NLPTutorRequestSerializer,
    ProjectIdeaRequestSerializer,
    # Import other serializers as you implement more views
)
from .services.ai_agent_client import ai_agent_client

class BaseAIAgentView(APIView):
    """
    Base view for AI Agent interactions, handling common exceptions.
    """
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        """
        Centralized exception handling for AI client calls.
        """
        if isinstance(exc, (ConnectionError, TimeoutError, ValueError)):
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        elif isinstance(exc, Exception):
            return Response({"error": "An internal server error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return super().handle_exception(exc)


class NLPTutorView(BaseAIAgentView):
    """
    API View to interact with the Personalized NLP Tutor AI Agent.
    """
    def post(self, request, *args, **kwargs):
        serializer = NLPTutorRequestSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        user = request.user

        # Create the profile snapshot expected by the AI agent service
        user_profile_snapshot = {
            "industry": user.industry,
            "profession": user.profession,
            "preferred_tutor_persona": user.profile.preferred_tutor_persona,
            "areas_of_interest": user.profile.areas_of_interest,
        }

        try:
            ai_response = ai_agent_client.call_nlp_tutor(
                user_id=str(user.id),
                query_text=validated_data['query_text'],
                user_profile_snapshot=user_profile_snapshot
            )
            return Response(ai_response, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_exception(e)


class ProjectIdeaGeneratorView(BaseAIAgentView):
    """
    API View to interact with the Project Idea Generator AI Agent.
    """
    def post(self, request, *args, **kwargs):
        serializer = ProjectIdeaRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        user = request.user

        user_profile_snapshot = {
            "industry": user.industry,
            "profession": user.profession,
            "preferred_tutor_persona": user.profile.preferred_tutor_persona,
            "areas_of_interest": user.profile.areas_of_interest,
        }

        try:
            ai_response = ai_agent_client.call_project_generator(
                user_id=str(user.id),
                course_context=validated_data.get('course_context', {}),
                user_profile_snapshot=user_profile_snapshot
            )
            return Response(ai_response, status=status.HTTP_200_OK)
        except Exception as e:
            return self.handle_exception(e)
