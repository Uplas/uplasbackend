from rest_framework import serializers
from .models import ProjectCategory, ProjectTag, Project, UserProject
from apps.courses.serializers import CourseSerializer # For associated_courses (basic info)
from apps.users.serializers import UserSerializer # For project created_by or user in UserProject

class ProjectCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectCategory
        fields = ['id', 'name', 'slug', 'description', 'icon_url']
        read_only_fields = ['id', 'slug']

class ProjectTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectTag
        fields = ['id', 'name', 'slug']
        read_only_fields = ['id', 'slug']

class ProjectSerializer(serializers.ModelSerializer): # For listing and general project info
    category = ProjectCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ProjectCategory.objects.all(), source='category', write_only=True, allow_null=True, required=False
    )
    tags = ProjectTagSerializer(many=True, read_only=True)
    # For creating/updating, tags might be a list of IDs or names
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProjectTag.objects.all(), source='tags', many=True, write_only=True, required=False
    )
    associated_courses = CourseSerializer(many=True, read_only=True, fields=['id', 'title', 'slug', 'cover_image_url']) # Basic course info
    created_by = UserSerializer(read_only=True, fields=['id', 'username', 'full_name'])
    
    # User-specific status for this project (e.g., if they've started it)
    user_status = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'title', 'slug', 'subtitle', 'description_html',
            'category', 'category_id', 'tags', 'tag_ids', 'difficulty_level',
            'estimated_duration', 'learning_objectives_html', 'requirements_html',
            'cover_image_url', 'associated_courses', 'project_source',
            'is_published', 'is_featured', 'created_by', 'created_at', 'updated_at',
            'ai_generated_spec_json', # Included for transparency or admin use
            'user_status'
        ]
        read_only_fields = ['id', 'slug', 'created_by', 'created_at', 'updated_at', 'user_status']
        # ai_generated_spec_json might be writable by AI agent or admin
    
    def get_user_status(self, obj: Project) -> str | None:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            try:
                user_project = UserProject.objects.get(user=user, project=obj)
                return user_project.get_status_display()
            except UserProject.DoesNotExist:
                return "Not Started" # Or None, depending on desired representation
        return None

    def create(self, validated_data):
        # Tags and associated_courses (M2M) need to be handled after instance creation if passed by ID
        tags_data = validated_data.pop('tags', None) # Assuming 'tags' is used as source for tag_ids
        # associated_courses_data = validated_data.pop('associated_courses', None)
        
        project = Project.objects.create(**validated_data)

        if tags_data:
            project.tags.set(tags_data)
        # if associated_courses_data:
        #     project.associated_courses.set(associated_courses_data)
        return project

class UserProjectSerializer(serializers.ModelSerializer): # For user's specific project instance
    project = ProjectSerializer(read_only=True) # Full project details nested
    project_id = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(), source='project', write_only=True
    )
    user = UserSerializer(read_only=True, fields=['id', 'username'])
    status_display = serializers.CharField(source='get_status_display', read_only=True)


    class Meta:
        model = UserProject
        fields = [
            'id', 'user', 'project', 'project_id', 'status', 'status_display',
            'started_at', 'submitted_at', 'completed_at',
            'submission_data_json', 'project_repository_url', # Choose one or allow multiple for submission
            'assessment_score', 'assessment_feedback_html',
            'last_accessed_at'
        ]
        read_only_fields = [
            'id', 'user', 'project', 'status_display', 'started_at', 'submitted_at',
            'completed_at', 'assessment_score', 'assessment_feedback_html', 'last_accessed_at'
        ]
        # 'status' can be updated by user actions (start, submit) or system (assessment)
        # 'submission_data_json'/'project_repository_url' are writable on submit.

class UserProjectStartSerializer(serializers.Serializer):
    # No fields needed, project is identified by URL, user by auth
    pass

class UserProjectSubmitSerializer(serializers.Serializer):
    # Define based on how submissions are handled (e.g. by UProjeX IDE panel)
    # Option 1: If IDE panel sends code as JSON
    submission_files = serializers.JSONField(required=False, help_text="e.g., {'filename.py': 'code content', ...}")
    # Option 2: If IDE panel provides a link to a GCS location or Git repo
    repository_url = serializers.URLField(required=False)
    # Option 3: A general JSON field for flexibility
    submission_data = serializers.JSONField(required=False)

    def validate(self, data):
        if not data.get('submission_files') and not data.get('repository_url') and not data.get('submission_data'):
            raise serializers.ValidationError("At least one submission method (files, repository URL, or data) is required.")
        # Add more specific validation based on the chosen submission method
        return data
