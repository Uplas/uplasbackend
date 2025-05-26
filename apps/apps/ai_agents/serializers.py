# apps/ai_agents/serializers.py
from rest_framework import serializers

# --- Tutor Serializers ---
class TutorQuestionSerializer(serializers.Serializer):
    question_text = serializers.CharField(max_length=2000)
    module_context = serializers.CharField(required=False, allow_blank=True)
    topic_context = serializers.CharField(required=False, allow_blank=True)
    # Add any other fields the tutor service expects

class TutorResponseSerializer(serializers.Serializer):
    answer_text = serializers.CharField()
    confidence_score = serializers.FloatField(required=False)
    # Add other fields the tutor service returns

# --- TTS Serializers ---
class TTSRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=5000)
    voice_character = serializers.CharField(required=False, max_length=50)
    # language = serializers.CharField(required=False, max_length=10) # Handled from user preference

class TTSResponseSerializer(serializers.Serializer):
    audio_url = serializers.URLField(required=False)
    audio_base64 = serializers.CharField(required=False) # If returning audio directly
    status = serializers.CharField(default='success')
    message = serializers.CharField(required=False)

# --- TTV Serializers ---
class TTVRequestSerializer(serializers.Serializer):
    script_text = serializers.CharField(max_length=10000)
    instructor_character = serializers.CharField(max_length=50, required=False) # e.g., 'Uncle Trevor', 'Susan'
    module_info = serializers.JSONField(required=False) # e.g., module title, objectives
    topic_info = serializers.JSONField(required=False)  # e.g., topic title, key concepts

class TTVResponseSerializer(serializers.Serializer):
    video_url = serializers.URLField(required=False)
    generation_status = serializers.CharField(default='pending') # e.g., pending, processing, completed, failed
    estimated_time_seconds = serializers.IntegerField(required=False)
    message = serializers.CharField(required=False)

# --- Project Idea Generator Serializers ---
class ProjectIdeaRequestSerializer(serializers.Serializer):
    course_context = serializers.CharField(required=False, allow_blank=True)
    topic_context = serializers.CharField(required=False, allow_blank=True)
    # user_interests, current_skills will be fetched from user profile in view

class ProjectIdeaResponseSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField()
    difficulty_level = serializers.CharField(max_length=50)
    estimated_duration_hours = serializers.IntegerField(required=False)
    learning_outcomes = serializers.ListField(child=serializers.CharField(), required=False)
    prerequisites = serializers.ListField(child=serializers.CharField(), required=False)
    technologies_suggested = serializers.ListField(child=serializers.CharField(), required=False)
    # ... any other fields your project generator AI provides

# --- Project Assessment Serializers ---
from apps.projects.models import ProjectSubmission # Assuming ProjectSubmission model is in apps.projects
class ProjectAssessmentRequestSerializer(serializers.Serializer):
    # This serializer is for the request FROM UPLAS frontend TO THIS backend view.
    user_project_submission_id = serializers.UUIDField()
    # The view will then fetch details from this submission to send to the AI service.

    def validate_user_project_submission_id(self, value):
        try:
            submission = ProjectSubmission.objects.get(pk=value, user_project__user=self.context['request'].user)
            # Ensure the submission is in a state that can be assessed (e.g., 'submitted')
            if submission.user_project.status != 'submitted':
                 raise serializers.ValidationError("This project submission is not in a submittable state for assessment.")
            self.context['user_project_submission_instance'] = submission # Pass instance to view
            return submission # Return the instance
        except ProjectSubmission.DoesNotExist:
            raise serializers.ValidationError("Project submission not found or you do not have permission to access it.")


class ProjectAssessmentResponseSerializer(serializers.Serializer):
    # This serializer is for the response FROM the external AI assessment service.
    submission_id = serializers.CharField() # The ID of the submission assessed by AI
    score = serializers.FloatField(min_value=0, max_value=100)
    passed = serializers.BooleanField()
    feedback_summary = serializers.CharField()
    detailed_feedback = serializers.JSONField(required=False) # e.g., criteria breakdown
    assessor_ai_agent_name = serializers.CharField(required=False, max_length=100)
