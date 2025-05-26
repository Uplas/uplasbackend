# apps/ai_agents/serializers.py
from rest_framework import serializers
from apps.projects.models import ProjectSubmission, UserProject # Import necessary models
from apps.users.models import UserProfile # Import UserProfile
from django.utils.translation import gettext_lazy as _

# --- Base AI Service Serializers ---
class AIRequestErrorSerializer(serializers.Serializer):
    """Standard format for reporting errors from AI service calls."""
    error = serializers.CharField()
    details = serializers.CharField(required=False, allow_blank=True)
    service_status_code = serializers.IntegerField(required=False)

# --- Tutor Serializers ---
class TutorQuestionSerializer(serializers.Serializer):
    question_text = serializers.CharField(max_length=2000, help_text=_("The user's question for the AI tutor."))
    module_context = serializers.CharField(required=False, allow_blank=True, help_text=_("Context from the current module."))
    topic_context = serializers.CharField(required=False, allow_blank=True, help_text=_("Context from the current topic."))
    session_id = serializers.CharField(required=False, allow_blank=True, help_text=_("Optional session ID for conversation history."))

class TutorResponseSerializer(serializers.Serializer):
    answer_text = serializers.CharField(help_text=_("The AI tutor's generated answer."))
    confidence_score = serializers.FloatField(required=False, help_text=_("AI's confidence in the answer."))
    related_topics = serializers.ListField(child=serializers.CharField(), required=False, help_text=_("Suggested related topics."))
    session_id = serializers.CharField(required=False, allow_blank=True)

# --- TTS Serializers ---
class TTSRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=5000, help_text=_("Text to convert to speech."))
    voice_character = serializers.CharField(required=False, max_length=50, help_text=_("Preferred voice (e.g., 'Uncle Trevor', 'Susan', 'alloy')."))
    language = serializers.CharField(required=False, max_length=10, help_text=_("Language code (e.g., 'en-US')."))

class TTSResponseSerializer(serializers.Serializer):
    audio_url = serializers.URLField(required=False, help_text=_("URL to the generated audio file."))
    audio_base64 = serializers.CharField(required=False, help_text=_("Base64 encoded audio data (if URL not provided)."))
    status = serializers.CharField(default='success', help_text=_("Status of the TTS generation."))
    message = serializers.CharField(required=False, allow_blank=True)

# --- TTV Serializers ---
class TTVRequestSerializer(serializers.Serializer):
    script_text = serializers.CharField(max_length=10000, help_text=_("The script for the video explanation."))
    instructor_character = serializers.CharField(max_length=50, required=False, help_text=_("Instructor ('Uncle Trevor', 'Susan')."))
    module_info = serializers.JSONField(required=False, help_text=_("JSON object with module context."))
    topic_info = serializers.JSONField(required=False, help_text=_("JSON object with topic context."))

class TTVResponseSerializer(serializers.Serializer):
    video_url = serializers.URLField(required=False, help_text=_("URL to the generated video file."))
    generation_status = serializers.CharField(default='pending', help_text=_("Status: pending, processing, completed, failed."))
    job_id = serializers.CharField(required=False, help_text=_("Job ID to check status later if asynchronous."))
    message = serializers.CharField(required=False, allow_blank=True)

# --- Project Idea Generator Serializers ---
class ProjectIdeaRequestSerializer(serializers.Serializer):
    course_context = serializers.CharField(required=False, allow_blank=True, help_text=_("Context from the course."))
    topic_context = serializers.CharField(required=False, allow_blank=True, help_text=_("Context from the topic."))
    # User interests/skills are added in the view.

class ProjectIdeaResponseSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField()
    difficulty_level = serializers.CharField(max_length=50)
    estimated_duration_hours = serializers.IntegerField(required=False)
    learning_outcomes = serializers.ListField(child=serializers.CharField(), required=False)
    prerequisites = serializers.ListField(child=serializers.CharField(), required=False)
    technologies_suggested = serializers.ListField(child=serializers.CharField(), required=False)

# --- Project Assessment Serializers ---
class ProjectAssessmentRequestSerializer(serializers.Serializer):
    user_project_submission_id = serializers.UUIDField(help_text=_("The ID of the UserProjectSubmission to be assessed."))

    def validate_user_project_submission_id(self, value):
        request = self.context['request']
        try:
            submission = ProjectSubmission.objects.select_related('user_project__project', 'user_project__user').get(
                pk=value,
                user_project__user=request.user
            )
            # You might want to check if it's already being assessed or has been assessed.
            # For now, we only check if it's submitted.
            if submission.status not in ['submitted', 'failed']: # Allow reassessment on 'failed'
                 raise serializers.ValidationError(_("This project submission is not in a state ready for assessment."))
            self.context['submission_instance'] = submission # Pass instance to view
            return value # Return the ID
        except ProjectSubmission.DoesNotExist:
            raise serializers.ValidationError(_("Project submission not found or you do not have permission to access it."))

class ProjectAssessmentResponseSerializer(serializers.Serializer):
    """Serializer for the response *from* the AI assessment service."""
    submission_id = serializers.CharField()
    score = serializers.FloatField(min_value=0, max_value=100)
    passed = serializers.BooleanField()
    feedback_summary = serializers.CharField()
    detailed_feedback = serializers.JSONField(required=False) # e.g., {'criterion1': {'score': 80, 'notes': 'Good'}, ...}
    assessor_ai_agent_name = serializers.CharField(required=False, max_length=100)
