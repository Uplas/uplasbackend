# apps/ai_agents/views.py
import requests
import logging
from django.conf import settings
from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import (
    TutorQuestionSerializer, TutorResponseSerializer,
    TTSRequestSerializer, TTSResponseSerializer,
    TTVRequestSerializer, TTVResponseSerializer,
    ProjectIdeaRequestSerializer, ProjectIdeaResponseSerializer,
    ProjectAssessmentRequestSerializer, ProjectAssessmentResponseSerializer,
    AIRequestErrorSerializer
)
from apps.users.models import UserProfile # Need UserProfile for personalization data
from apps.projects.models import ProjectAssessment, ProjectSubmission # For saving assessment results

# Get an instance of a logger
logger = logging.getLogger(__name__)

# --- Centralized AI Service Call Function ---
def call_ai_service(service_url, method='post', data=None, timeout=60):
    """
    Calls an external AI service with standardized error handling.

    Args:
        service_url (str): The URL of the AI service endpoint.
        method (str): HTTP method ('post' or 'get').
        data (dict): Payload for 'post' or params for 'get'.
        timeout (int): Request timeout in seconds.

    Returns:
        tuple: (response_data, error_response_data, status_code)
               On success, (response_data, None, status_code).
               On failure, (None, error_response_data, status_code).
    """
    if not service_url:
        logger.error("AI service URL is not configured.")
        return None, {"error": "AI service URL not configured."}, status.HTTP_501_NOT_IMPLEMENTED

    headers = {}
    if settings.AI_SERVICE_API_KEY:
        headers['Authorization'] = f'Bearer {settings.AI_SERVICE_API_KEY}'
    headers['Content-Type'] = 'application/json'
    headers['Accept'] = 'application/json'

    try:
        logger.info(f"Calling AI service: {service_url} with method: {method}")
        if method.lower() == 'post':
            response = requests.post(service_url, json=data, headers=headers, timeout=timeout)
        elif method.lower() == 'get':
            response = requests.get(service_url, params=data, headers=headers, timeout=timeout)
        else:
            logger.error(f"Unsupported HTTP method: {method}")
            return None, {"error": "Unsupported HTTP method"}, status.HTTP_501_NOT_IMPLEMENTED

        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        
        try:
            response_json = response.json()
            logger.info(f"AI service call successful. Status: {response.status_code}")
            return response_json, None, response.status_code
        except ValueError: # If response is not JSON
            logger.error(f"AI service returned non-JSON response. Status: {response.status_code}. Response: {response.text[:200]}...")
            return None, {"error": "AI service returned non-JSON response.", "details": response.text}, response.status_code

    except requests.exceptions.Timeout:
        logger.warning(f"AI service call timed out: {service_url}")
        return None, {"error": "Request to AI service timed out."}, status.HTTP_504_GATEWAY_TIMEOUT
    except requests.exceptions.ConnectionError as e:
        logger.error(f"AI service connection error: {service_url}. Error: {e}")
        return None, {"error": "Could not connect to AI service."}, status.HTTP_503_SERVICE_UNAVAILABLE
    except requests.exceptions.HTTPError as e:
        error_detail = {"error": f"AI service returned an error: {e.response.status_code}"}
        try:
            error_detail.update(e.response.json())
        except ValueError:
            error_detail["details"] = e.response.text[:500] # Limit raw response size
        logger.warning(f"AI service HTTP error: {service_url}. Status: {e.response.status_code}. Details: {error_detail}")
        return None, error_detail, e.response.status_code
    except Exception as e:
        logger.critical(f"Unexpected error calling AI service: {service_url}. Error: {e}", exc_info=True)
        return None, {"error": f"An unexpected error occurred: {str(e)}"}, status.HTTP_500_INTERNAL_SERVER_ERROR

# --- Base AI View ---
class BaseAIAgentView(views.APIView):
    """Base view for handling AI agent requests."""
    permission_classes = [IsAuthenticated]
    request_serializer_class = None
    response_serializer_class = None
    ai_service_url_setting = None
    ai_service_endpoint = "" # Specific path like '/ask' or '/generate'

    def get_ai_service_url(self):
        base_url = getattr(settings, self.ai_service_url_setting, None)
        return base_url + self.ai_service_endpoint if base_url else None

    def build_payload(self, request, validated_data):
        """Build the payload to send to the AI service. Needs personalization."""
        user = request.user
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            profile = None # Handle cases where profile might not exist yet

        payload = {
            'user_id': str(user.id),
            'user_profile_data': {
                'career': getattr(user, 'profession', None) or getattr(user, 'career_interest', None),
                'location': getattr(user, 'city', None) or getattr(user, 'country', None),
                'industry': getattr(user, 'industry', None),
                'learning_goals': getattr(profile, 'learning_goals', None) if profile else None,
                'preferred_language': getattr(user, 'preferred_language', 'en'),
                'interests': getattr(profile, 'areas_of_interest', None) if profile else None,
            },
            **validated_data # Add validated data from the request
        }
        return payload

    def process_ai_response(self, ai_response_data, request, validated_data):
        """Hook to process the AI response before sending it back or saving."""
        return ai_response_data # Default: just return it

    def post(self, request, *args, **kwargs):
        if not self.request_serializer_class:
            return Response({"error": "View not configured correctly (request_serializer_class missing)."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.request_serializer_class(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payload = self.build_payload(request, serializer.validated_data)
        service_url = self.get_ai_service_url()

        ai_response, error_data, status_code = call_ai_service(service_url, data=payload)

        if error_data:
            return Response(error_data, status=status_code)

        # Process the response (e.g., save assessment)
        processed_response = self.process_ai_response(ai_response, request, serializer.validated_data)


        if not self.response_serializer_class:
             return Response({"error": "View not configured correctly (response_serializer_class missing)."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response_serializer = self.response_serializer_class(data=processed_response)
        if response_serializer.is_valid():
            return Response(response_serializer.validated_data, status=status.HTTP_200_OK)
        else:
            logger.error(f"Invalid response format from AI service ({service_url}) or processing. Errors: {response_serializer.errors}")
            return Response({"error": "Invalid response format from AI service.", "details": response_serializer.errors}, status.HTTP_500_INTERNAL_SERVER_ERROR)

# --- Specific Views ---
class AskAITutorView(BaseAIAgentView):
    request_serializer_class = TutorQuestionSerializer
    response_serializer_class = TutorResponseSerializer
    ai_service_url_setting = 'AI_NLP_TUTOR_SERVICE_URL'
    ai_service_endpoint = "/ask" # Assuming this endpoint

ask_ai_tutor_view = AskAITutorView.as_view()

class GenerateTTSView(BaseAIAgentView):
    request_serializer_class = TTSRequestSerializer
    response_serializer_class = TTSResponseSerializer
    ai_service_url_setting = 'AI_TTS_SERVICE_URL'
    ai_service_endpoint = "/generate"

generate_tts_view = GenerateTTSView.as_view()

class GenerateTTVView(BaseAIAgentView):
    request_serializer_class = TTVRequestSerializer
    response_serializer_class = TTVResponseSerializer
    ai_service_url_setting = 'AI_TTV_SERVICE_URL'
    ai_service_endpoint = "/generate"

generate_ttv_view = GenerateTTVView.as_view()

class GenerateProjectIdeaView(BaseAIAgentView):
    request_serializer_class = ProjectIdeaRequestSerializer
    response_serializer_class = ProjectIdeaResponseSerializer
    ai_service_url_setting = 'AI_PROJECT_GENERATOR_SERVICE_URL'
    ai_service_endpoint = "/generate-idea"

generate_project_idea_view = GenerateProjectIdeaView.as_view()

class AssessProjectView(BaseAIAgentView):
    request_serializer_class = ProjectAssessmentRequestSerializer
    response_serializer_class = ProjectAssessmentResponseSerializer # Response from AI
    ai_service_url_setting = 'AI_PROJECT_ASSESSMENT_SERVICE_URL'
    ai_service_endpoint = "/assess"

    def build_payload(self, request, validated_data):
        """Override to build payload specific to assessment."""
        submission = self.context['submission_instance'] # Get instance from serializer validation
        payload = {
            'submission_id': str(submission.id),
            'repository_url': submission.submission_artifacts.get('repository_url'),
            'live_url': submission.submission_artifacts.get('live_demo_url'),
            'project_definition_id': str(submission.user_project.project_id),
            'project_title': submission.user_project.project.title,
            'project_guidelines': submission.user_project.project.guidelines,
            'user_id': str(request.user.id),
        }
        return payload

    def process_ai_response(self, ai_response_data, request, validated_data):
        """Override to save the assessment result."""
        submission = self.context['submission_instance']
        
        # We need to validate the AI response before saving
        assessment_serializer = ProjectAssessmentResponseSerializer(data=ai_response_data)
        if assessment_serializer.is_valid():
            assessment_data = assessment_serializer.validated_data
            try:
                # Use update_or_create to handle re-assessments
                assessment, created = ProjectAssessment.objects.update_or_create(
                    submission=submission,
                    defaults={
                        'assessed_by_ai': True,
                        'assessor_ai_agent_name': assessment_data.get('assessor_ai_agent_name', 'UPLAS AI Assessor'),
                        'score': assessment_data['score'],
                        'passed': assessment_data['passed'],
                        'feedback_summary': assessment_data['feedback_summary'],
                        'detailed_feedback': assessment_data.get('detailed_feedback', {}),
                        'status': 'completed',
                    }
                )
                logger.info(f"Project assessment {'created' if created else 'updated'} for submission {submission.id}.")
                # The ProjectAssessment model's save() method should handle updating UserProject status.
                return assessment_data # Return the validated data
            except Exception as e:
                logger.error(f"Failed to save project assessment for {submission.id}. Error: {e}", exc_info=True)
                # This should ideally return an error response, but BaseAIAgentView handles that.
                # We raise an exception here or return something that indicates failure.
                # For now, we'll let it fall through and potentially fail the response serialization.
                # A better way might be to add error handling here.
                return {"error": "Failed to save assessment results."} # Return an error structure
        else:
            logger.error(f"AI Assessment service returned invalid data: {assessment_serializer.errors}")
            return {"error": "Invalid response format from AI Assessment service.", "details": assessment_serializer.errors}


assess_project_view = AssessProjectView.as_view()
