# apps/ai_agents/views.py
import requests # Or httpx for async if needed
from django.conf import settings
from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import ( # Define these serializers
    TutorQuestionSerializer, TutorResponseSerializer,
    TTSRequestSerializer, TTSResponseSerializer,
    TTVRequestSerializer, TTVResponseSerializer,
    ProjectIdeaRequestSerializer, ProjectIdeaResponseSerializer,
    ProjectAssessmentRequestSerializer, ProjectAssessmentResponseSerializer
)

# --- Helper function to call external AI service ---
def call_ai_service(service_url, method='post', data=None, headers=None, timeout=30):
    default_headers = {}
    if settings.AI_SERVICE_API_KEY: # If you use an API key for your internal AI services
        default_headers['Authorization'] = f'Bearer {settings.AI_SERVICE_API_KEY}'
    if headers:
        default_headers.update(headers)

    try:
        if method.lower() == 'post':
            response = requests.post(service_url, json=data, headers=default_headers, timeout=timeout)
        elif method.lower() == 'get':
            response = requests.get(service_url, params=data, headers=default_headers, timeout=timeout)
        # Add other methods if needed (PUT, DELETE)
        else:
            return None, {"error": "Unsupported HTTP method for AI service call"}, 500

        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        return response.json(), None, response.status_code
    except requests.exceptions.Timeout:
        return None, {"error": "Request to AI service timed out."}, status.HTTP_504_GATEWAY_TIMEOUT
    except requests.exceptions.ConnectionError:
        return None, {"error": "Could not connect to AI service."}, status.HTTP_503_SERVICE_UNAVAILABLE
    except requests.exceptions.HTTPError as e:
        # Try to get error details from AI service response if possible
        error_detail = {"error": f"AI service returned an error: {e.response.status_code}"}
        try:
            error_detail.update(e.response.json())
        except ValueError: # Not JSON
            error_detail["raw_response"] = e.response.text
        return None, error_detail, e.response.status_code
    except Exception as e: # Catch-all for other unexpected errors
        # Log this exception 'e'
        return None, {"error": f"An unexpected error occurred while communicating with AI service: {str(e)}"}, status.HTTP_500_INTERNAL_SERVER_ERROR


# --- AI Tutor View ---
class AskAITutorView(views.APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TutorQuestionSerializer # For request validation

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Prepare data for the AI Tutor service
        # Include user-specific data for personalization from request.user and request.user.profile
        payload = {
            'user_id': str(request.user.id),
            'user_profile_data': {
                'career': request.user.profession or request.user.career_interest,
                'location': request.user.city or request.user.country,
                'industry': request.user.industry,
                'other_industry_details': request.user.other_industry_details,
                'learning_goals': request.user.profile.learning_goals,
                # Add other relevant fields from User and UserProfile
            },
            'question_text': serializer.validated_data['question_text'],
            'module_context': serializer.validated_data.get('module_context'), # Optional
            'topic_context': serializer.validated_data.get('topic_context'),   # Optional
        }

        ai_response, error_data, status_code = call_ai_service(
            settings.AI_NLP_TUTOR_SERVICE_URL + "/ask", # Example endpoint
            data=payload
        )

        if error_data:
            return Response(error_data, status=status_code)
        
        # Validate and return the AI's response
        response_serializer = TutorResponseSerializer(data=ai_response)
        if response_serializer.is_valid():
            return Response(response_serializer.validated_data, status=status.HTTP_200_OK)
        else:
            # Log this: AI service returned unexpected format
            return Response({"error": "Invalid response format from AI Tutor service.", "details": response_serializer.errors}, status.HTTP_500_INTERNAL_SERVER_ERROR)

# Assign to the name used in urls.py
ask_ai_tutor_view = AskAITutorView.as_view()


# --- Text-to-Speech (TTS) View ---
class GenerateTTSView(views.APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TTSRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            'text_to_convert': serializer.validated_data['text'],
            'voice_character': serializer.validated_data.get('voice_character') or request.user.profile.preferred_tts_voice_character or 'alloy', # Default if none
            'language': request.user.preferred_language or 'en',
            # Add other parameters your TTS service might need
        }
        
        ai_response, error_data, status_code = call_ai_service(
            settings.AI_TTS_SERVICE_URL + "/generate",
            data=payload
        )

        if error_data:
            return Response(error_data, status=status_code)
        
        response_serializer = TTSResponseSerializer(data=ai_response)
        if response_serializer.is_valid():
            # The response might contain a URL to the audio file, or binary data
            return Response(response_serializer.validated_data, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid response format from TTS service.", "details": response_serializer.errors}, status.HTTP_500_INTERNAL_SERVER_ERROR)

generate_tts_view = GenerateTTSView.as_view()


# --- Text-to-Video (TTV) View ---
class GenerateTTVView(views.APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TTVRequestSerializer # text, module_data, user_data

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            'script_text': serializer.validated_data['script_text'],
            'instructor_character': serializer.validated_data.get('instructor_character') or request.user.profile.preferred_ttv_instructor or 'Uncle Trevor', # e.g., 'Uncle Trevor', 'Susan'
            'module_info': serializer.validated_data.get('module_info'), # Context for personalization
            'topic_info': serializer.validated_data.get('topic_info'),   # Context for personalization
            'user_profile_data': { # For personalized explanations
                'career': request.user.profession or request.user.career_interest,
                'learning_goals': request.user.profile.learning_goals,
            }
        }

        ai_response, error_data, status_code = call_ai_service(
            settings.AI_TTV_SERVICE_URL + "/generate",
            data=payload
        )
        if error_data:
            return Response(error_data, status=status_code)
        
        response_serializer = TTVResponseSerializer(data=ai_response)
        if response_serializer.is_valid():
            # Response might contain a URL to the video or status of generation
            return Response(response_serializer.validated_data, status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid response format from TTV service.", "details": response_serializer.errors}, status.HTTP_500_INTERNAL_SERVER_ERROR)

generate_ttv_view = GenerateTTVView.as_view()


# --- AI Project Generator View ---
class GenerateProjectIdeaView(views.APIView):
    permission_classes = [IsAuthenticated] # Or specific permission if project generation is restricted
    serializer_class = ProjectIdeaRequestSerializer # e.g., topic, user_interests

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        payload = {
            'user_id': str(request.user.id),
            'user_profile_data': {
                'industry': request.user.industry,
                'interests': request.user.profile.areas_of_interest,
                'current_skills': request.user.profile.current_knowledge_level,
            },
            'course_context': serializer.validated_data.get('course_context'), # Optional
            'topic_context': serializer.validated_data.get('topic_context'), # Optional
        }

        ai_response, error_data, status_code = call_ai_service(
            settings.AI_PROJECT_GENERATOR_SERVICE_URL + "/generate-idea",
            data=payload
        )
        if error_data:
            return Response(error_data, status=status_code)
            
        response_serializer = ProjectIdeaResponseSerializer(data=ai_response) # title, description, tech_stack, etc.
        if response_serializer.is_valid():
            # TODO: Optionally save this generated project idea to the Project model in this backend
            # (e.g., as an AI-generated, unpublished project definition for the user to start)
            # Project.objects.create(
            #     title=response_serializer.validated_data['title'],
            #     description=response_serializer.validated_data['description'],
            #     created_by=request.user, # Or a system AI user
            #     ai_generated=True,
            #     is_published=False,
            #     # ... map other fields ...
            # )
            return Response(response_serializer.validated_data, status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid response format from Project Generator service.", "details": response_serializer.errors}, status.HTTP_500_INTERNAL_SERVER_ERROR)

generate_project_idea_view = GenerateProjectIdeaView.as_view()


# --- AI Project Assessment View ---
class AssessProjectView(views.APIView):
    permission_classes = [IsAuthenticated] # User submitting their project
    serializer_class = ProjectAssessmentRequestSerializer # e.g., project_submission_id, repository_url

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_project_submission = serializer.validated_data['user_project_submission'] # This is the ProjectSubmission instance

        payload = {
            'submission_id': str(user_project_submission.id),
            'repository_url': user_project_submission.submission_artifacts.get('repository_url') or user_project_submission.user_project.repository_url,
            'live_url': user_project_submission.submission_artifacts.get('live_demo_url') or user_project_submission.user_project.live_url,
            'project_definition_id': str(user_project_submission.user_project.project_id),
            'project_title': user_project_submission.user_project.project.title,
            'project_guidelines': user_project_submission.user_project.project.guidelines, # Send guidelines for assessment
            'user_id': str(request.user.id),
        }

        ai_response, error_data, status_code = call_ai_service(
            settings.AI_PROJECT_ASSESSMENT_SERVICE_URL + "/assess",
            data=payload
        )
        if error_data:
            return Response(error_data, status=status_code)
        
        response_serializer = ProjectAssessmentResponseSerializer(data=ai_response) # score, feedback, passed_status
        if response_serializer.is_valid():
            # TODO: Save this assessment to the ProjectAssessment model in this backend
            # This is already handled by the `apps.projects.views.ProjectAssessmentViewSet.submit_ai_assessment`
            # So, this view might directly call that internal service method if the AI agent
            # is *also* calling back to this backend.
            # OR, if this view is what the UPLAS frontend calls, and then this view calls the external AI,
            # then this view should process the AI response and create the ProjectAssessment record.
            
            # For example, creating the ProjectAssessment record here:
            # from apps.projects.models import ProjectAssessment
            # assessment = ProjectAssessment.objects.create(
            #     submission=user_project_submission,
            #     assessed_by_ai=True,
            #     assessor_ai_agent_name=response_serializer.validated_data.get('assessor_ai_agent_name', 'UPLAS AI Assessor'),
            #     score=response_serializer.validated_data['score'],
            #     passed=response_serializer.validated_data['passed'],
            #     feedback_summary=response_serializer.validated_data['feedback_summary'],
            #     detailed_feedback=response_serializer.validated_data.get('detailed_feedback', {})
            # )
            # The save() method of ProjectAssessment model handles UserProject status update.

            # If the ProjectAssessmentViewSet's `submit-ai-assessment` action is the target for the AI service,
            # then this view might not be needed, or it's a passthrough.
            # Your `apps/projects/views.py` has ProjectAssessmentViewSet with `submit-ai-assessment` action.
            # It's better if the AI agent calls that endpoint directly.
            # This current view (`AssessProjectView` in `apps.ai_agents`) would be what the *UPLAS Frontend* calls
            # to initiate the assessment, which then calls the external AI. The AI service, upon completion,
            # would then call back to the `/api/projects/project-assessments/submit-ai-assessment/` endpoint.

            return Response(response_serializer.validated_data, status.HTTP_200_OK)
        else:
             return Response({"error": "Invalid response format from Project Assessment service.", "details": response_serializer.errors}, status.HTTP_500_INTERNAL_SERVER_ERROR)

assess_project_view = AssessProjectView.as_view()
