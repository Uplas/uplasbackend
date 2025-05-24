from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils.text import slugify # For generating slugs if needed

from .models import (
    ProjectTag, Project, UserProject, ProjectSubmission, ProjectAssessment,
    USER_PROJECT_STATUS_CHOICES, PROJECT_DIFFICULTY_CHOICES
)
# Assuming a simple user serializer might be needed from a shared app or users app
# from apps.users.serializers import SimpleUserSerializer # Example import
# For now, define a local one if not available globally
User = get_user_model()

class SimpleUserSerializer(serializers.ModelSerializer): # Define locally if not imported
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'email']


# --- ProjectTag Serializer ---
class ProjectTagSerializer(serializers.ModelSerializer):
    """
    Serializer for ProjectTag model.
    """
    class Meta:
        model = ProjectTag
        fields = ['id', 'name', 'slug', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_name(self, value):
        # Optionally, ensure slug is generated if not provided or update based on name
        # For now, assume slug is provided or handled by model/admin
        return value


# --- Project (Definition) Serializers ---
class ProjectListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing Project definitions (summary view).
    """
    technologies_used = ProjectTagSerializer(many=True, read_only=True)
    created_by = SimpleUserSerializer(read_only=True)
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)

    class Meta:
        model = Project
        fields = [
            'id', 'title', 'slug', 'short_description', # Assuming Project model has short_description
            'difficulty_level', 'difficulty_level_display', 'estimated_duration_hours',
            'technologies_used', 'is_published', 'ai_generated', 'created_by', 'created_at'
        ]
        # Add 'short_description' to Project model if it doesn't exist, or remove from here.
        # For now, assuming it might be part of the description or a separate field.
        # If no short_description, use description[:150] or similar in a SerializerMethodField.

    def get_short_description(self, obj): # Example if short_description is not a direct field
        if hasattr(obj, 'short_description_field') and obj.short_description_field:
             return obj.short_description_field
        return obj.description[:150] + '...' if len(obj.description) > 150 else obj.description


class ProjectDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed view of a Project definition.
    """
    technologies_used = ProjectTagSerializer(many=True, read_only=True)
    # For write operations, allow setting tags by ID
    technology_tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProjectTag.objects.all(), source='technologies_used',
        many=True, write_only=True, required=False
    )
    created_by = SimpleUserSerializer(read_only=True)
    # created_by_id = serializers.PrimaryKeyRelatedField( # Only if admin can set it
    #     queryset=User.objects.all(), source='created_by', write_only=True, required=False, allow_null=True
    # )
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)


    class Meta:
        model = Project
        fields = [
            'id', 'title', 'slug', 'description', 'difficulty_level', 'difficulty_level_display',
            'estimated_duration_hours', 'learning_outcomes', 'prerequisites',
            'technologies_used', 'technology_tag_ids', 'guidelines', 'resources',
            'is_published', 'created_by', #'created_by_id',
            'ai_generated', 'ai_generation_prompt',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at', 'technologies_used']
        extra_kwargs = {
            'slug': {'required': False}, # Can be auto-generated from title
            'ai_generation_prompt': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def create(self, validated_data):
        # Set created_by to the request user if not an admin setting it explicitly
        if 'created_by' not in validated_data and self.context['request'].user.is_authenticated:
            validated_data['created_by'] = self.context['request'].user

        if 'slug' not in validated_data or not validated_data['slug']:
            validated_data['slug'] = slugify(validated_data['title'])
            # Ensure slug uniqueness if auto-generating
            original_slug = validated_data['slug']
            counter = 1
            while Project.objects.filter(slug=validated_data['slug']).exists():
                validated_data['slug'] = f"{original_slug}-{counter}"
                counter += 1
        
        # Handle ManyToMany for technology_tag_ids
        tags_data = validated_data.pop('technologies_used', None) # source='technologies_used' for technology_tag_ids
        project = Project.objects.create(**validated_data)
        if tags_data:
            project.technologies_used.set(tags_data)
        return project

    def update(self, instance, validated_data):
        if 'slug' not in validated_data or not validated_data.get('slug'):
            if 'title' in validated_data and validated_data['title'] != instance.title:
                new_slug = slugify(validated_data['title'])
                # Check uniqueness if slug changes
                if new_slug != instance.slug and Project.objects.filter(slug=new_slug).exclude(pk=instance.pk).exists():
                    original_slug = new_slug
                    counter = 1
                    while Project.objects.filter(slug=new_slug).exclude(pk=instance.pk).exists():
                        new_slug = f"{original_slug}-{counter}"
                        counter += 1
                validated_data['slug'] = new_slug
        
        # Handle ManyToMany for technology_tag_ids
        if 'technologies_used' in validated_data: # This key comes from source='technologies_used'
            tags_data = validated_data.pop('technologies_used')
            instance.technologies_used.set(tags_data)

        return super().update(instance, validated_data)


# --- UserProject (Instance) Serializers ---
class UserProjectListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing UserProject instances (summary view).
    """
    project_title = serializers.CharField(source='project.title', read_only=True)
    project_slug = serializers.CharField(source='project.slug', read_only=True)
    project_difficulty = serializers.CharField(source='project.get_difficulty_level_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True) # For admin views

    class Meta:
        model = UserProject
        fields = [
            'id', 'user_email', 'project_id', 'project_title', 'project_slug', 'project_difficulty',
            'status', 'status_display', 'started_at', 'completed_at', 'updated_at'
        ]

class UserProjectDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed view of a UserProject instance.
    """
    user = SimpleUserSerializer(read_only=True)
    project = ProjectDetailSerializer(read_only=True) # Show full project definition details
    project_id = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.filter(is_published=True), # User can only start published projects
        source='project', write_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # Submissions and assessments could be nested or linked via separate endpoints
    # For simplicity, we might not nest them directly here to avoid overly large payloads.

    class Meta:
        model = UserProject
        fields = [
            'id', 'user', 'project', 'project_id', 'status', 'status_display',
            'started_at', 'completed_at', 'repository_url', 'live_url',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'project', 'started_at', 'completed_at', 'created_at', 'updated_at']
        # Status might be updated by user actions (e.g., starting) or system (submission, assessment)
        # repository_url and live_url are writable by the user.

    def validate_project_id(self, value):
        # User can only create a UserProject for a published Project
        if not value.is_published:
            raise serializers.ValidationError(_("Cannot start a project that is not published."))
        return value

    def validate(self, data):
        request = self.context.get('request')
        user = request.user if request else None
        project = data.get('project') # This will be the Project instance after validate_project_id

        if not self.instance: # Creating a new UserProject
            if UserProject.objects.filter(user=user, project=project).exists():
                raise serializers.ValidationError(_("You have already started this project."))
        return data

    def create(self, validated_data):
        # User is set from the request context in the view
        if 'user' not in validated_data and self.context['request'].user.is_authenticated:
            validated_data['user'] = self.context['request'].user
        
        # Default status is 'not_started', if user explicitly starts it, status might be 'in_progress'
        if validated_data.get('status') == 'in_progress':
            validated_data['started_at'] = timezone.now()
            
        return super().create(validated_data)


# --- ProjectSubmission Serializers ---
class ProjectSubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for ProjectSubmission model.
    """
    user_project_id = serializers.PrimaryKeyRelatedField(
        queryset=UserProject.objects.all(), source='user_project', write_only=True
    )
    user_project_title = serializers.CharField(source='user_project.project.title', read_only=True)
    user_email = serializers.EmailField(source='user_project.user.email', read_only=True)

    class Meta:
        model = ProjectSubmission
        fields = [
            'id', 'user_project_id', 'user_project_title', 'user_email',
            'submitted_at', 'submission_notes', 'submission_artifacts',
            'submission_version'
        ]
        read_only_fields = ['id', 'submitted_at', 'submission_version', 'user_project_title', 'user_email']

    def validate_user_project_id(self, value): # value is UserProject instance
        request = self.context.get('request')
        user = request.user
        # Check if the user owns this UserProject (or is admin)
        if value.user != user and not user.is_staff:
            raise serializers.ValidationError(_("You can only submit to your own projects."))
        # Check if project is in a submittable state
        if value.status not in ['in_progress', 'failed', 'submitted']: # 'submitted' for re-submission
            raise serializers.ValidationError(_(f"Project is not in a submittable state. Current status: {value.get_status_display()}"))
        return value

    # create() method in view will set user_project based on context/URL and save.
    # The model's save() method handles updating UserProject status and version.


# --- ProjectAssessment Serializers ---
class ProjectAssessmentSerializer(serializers.ModelSerializer):
    """
    Serializer for ProjectAssessment model.
    """
    submission_id = serializers.PrimaryKeyRelatedField(
        queryset=ProjectSubmission.objects.all(), source='submission', write_only=True
    )
    # Display related info for context
    submission_details = serializers.SerializerMethodField(read_only=True)
    assessed_by_display = serializers.SerializerMethodField(read_only=True)


    class Meta:
        model = ProjectAssessment
        fields = [
            'id', 'submission_id', 'submission_details', 'assessed_by_ai', 'assessor_ai_agent_name',
            'manual_assessor', 'score', 'passed', 'feedback_summary',
            'detailed_feedback', 'assessed_at', 'assessed_by_display'
        ]
        read_only_fields = ['id', 'assessed_at', 'submission_details', 'assessed_by_display']
        # `manual_assessor` might be set if an admin is creating/editing.
        # `assessed_by_ai`, `assessor_ai_agent_name`, `score`, `passed`, `feedback` are typically set by AI/Admin.

    def get_submission_details(self, obj):
        if obj.submission:
            return {
                "submission_id": obj.submission.id,
                "user_project_title": obj.submission.user_project.project.title,
                "user_email": obj.submission.user_project.user.email,
                "submitted_at": obj.submission.submitted_at
            }
        return None

    def get_assessed_by_display(self, obj):
        if obj.assessed_by_ai and obj.assessor_ai_agent_name:
            return f"AI: {obj.assessor_ai_agent_name}"
        if obj.manual_assessor:
            return f"Manual: {obj.manual_assessor.get_full_name() or obj.manual_assessor.email}"
        if obj.assessed_by_ai:
            return "AI (Generic)"
        return "N/A"

    def create(self, validated_data):
        # Logic for updating UserProject status is in ProjectAssessment.save() model method.
        # If manual_assessor is not provided but user is staff, set them as manual_assessor.
        request = self.context.get('request', None)
        if request and request.user.is_staff and 'manual_assessor' not in validated_data and not validated_data.get('assessed_by_ai', False):
            validated_data['manual_assessor'] = request.user
        
        assessment = super().create(validated_data)
        # The model's save method handles updating UserProject status.
        return assessment

    def update(self, instance, validated_data):
        assessment = super().update(instance, validated_data)
        # The model's save method handles updating UserProject status.
        return assessment
