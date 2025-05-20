from rest_framework import serializers
from django.contrib.auth import get_user_model # For BasicUserSerializerForProjects

from .models import ProjectCategory, ProjectTag, Project, UserProject
# Assuming CourseSerializer and UserSerializer are in their respective apps
# We'll use basic serializers for nesting to avoid circular dependencies or overly complex data.

User = get_user_model()

# If BasicUserSerializer and BasicCourseSerializer are not defined elsewhere for tests,
# include minimal versions here.
class BasicUserSerializerForProjects(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'profile_picture_url'] # Essential display fields
        read_only_fields = fields

# Assuming apps.courses.models.Course exists for BasicCourseSerializerForProjects
# from apps.courses.models import Course as CourseModel # Renaming to avoid conflict
# For testing purposes, if apps.courses.models.Course is not easily mockable/importable:
class DummyCourseModelForSerializer: # Mock enough for serializer
    def __init__(self, id, title, slug, cover_image_url):
        self.id = id
        self.title = title
        self.slug = slug
        self.cover_image_url = cover_image_url

class BasicCourseSerializerForProjects(serializers.Serializer): # Not ModelSerializer if using Dummy
    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    cover_image_url = serializers.URLField(read_only=True)
    # Add other fields if your ProjectSerializer's nested CourseSerializer needs them
    # Example from previous output: fields=['id', 'title', 'slug', 'cover_image_url']

    # If using actual CourseModel:
    # class Meta:
    #     model = CourseModel # Use the actual Course model from apps.courses.models
    #     fields = ['id', 'title', 'slug', 'cover_image_url']
    #     read_only_fields = fields


class ProjectCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectCategory
        fields = ['id', 'name', 'slug', 'description', 'icon_url', 'created_at', 'updated_at']
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']

class ProjectTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectTag
        fields = ['id', 'name', 'slug', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at']

class ProjectSerializer(serializers.ModelSerializer):
    category = ProjectCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ProjectCategory.objects.all(), source='category',
        write_only=True, allow_null=True, required=False
    )
    tags = ProjectTagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProjectTag.objects.all(), source='tags',
        many=True, write_only=True, required=False
    )
    associated_courses = BasicCourseSerializerForProjects(many=True, read_only=True)
    # associated_course_ids = serializers.PrimaryKeyRelatedField(
    #     queryset=CourseModel.objects.all(), source='associated_courses', # Use actual Course model
    #     many=True, write_only=True, required=False
    # )
    created_by = BasicUserSerializerForProjects(read_only=True)
    
    user_status = serializers.SerializerMethodField()
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)
    project_source_display = serializers.CharField(source='get_project_source_display', read_only=True)


    class Meta:
        model = Project
        fields = [
            'id', 'title', 'slug', 'subtitle', 'description_html',
            'category', 'category_id', 'tags', 'tag_ids',
            'difficulty_level', 'difficulty_level_display',
            'estimated_duration', 'learning_objectives_html', 'requirements_html',
            'cover_image_url', 'associated_courses', # 'associated_course_ids',
            'project_source', 'project_source_display',
            'is_published', 'is_featured', 'created_by',
            'created_at', 'updated_at',
            'ai_generated_spec_json',
            'user_status'
        ]
        read_only_fields = [
            'id', 'slug', 'created_by', 'created_at', 'updated_at', 'user_status',
            'difficulty_level_display', 'project_source_display', 'category', 'tags', 'associated_courses',
        ]
        extra_kwargs = { # For fields that are writable but need specific handling
            'ai_generated_spec_json': {'required': False, 'allow_null': True}
        }
    
    def get_user_status(self, obj: Project) -> str | None:
        user = self.context.get('request').user
        if hasattr(obj, 'user_project_status_annotated'): # Check for annotated field
            return obj.user_project_status_annotated
        
        if user and user.is_authenticated:
            try:
                user_project = UserProject.objects.get(user=user, project=obj)
                return user_project.get_status_display()
            except UserProject.DoesNotExist:
                return UserProject.STATUS_CHOICES[0][1] # 'Not Started' display value
        return None # Or 'Not Logged In'

    def create(self, validated_data):
        # Pop M2M fields before super().create()
        tags_data = validated_data.pop('tags', None) # 'tags' is the source for 'tag_ids'
        # associated_courses_data = validated_data.pop('associated_courses', None) # 'associated_courses' for 'associated_course_ids'
        
        project = super().create(validated_data)

        if tags_data: # tags_data will be a list of ProjectTag instances due to PrimaryKeyRelatedField
            project.tags.set(tags_data)
        # if associated_courses_data:
        #     project.associated_courses.set(associated_courses_data)
        return project

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        # associated_courses_data = validated_data.pop('associated_courses', None)
        
        instance = super().update(instance, validated_data)

        if tags_data is not None: # Allow clearing tags with empty list
            instance.tags.set(tags_data)
        # if associated_courses_data is not None:
        #     instance.associated_courses.set(associated_courses_data)
        return instance


class UserProjectSerializer(serializers.ModelSerializer):
    project = ProjectSerializer(read_only=True) # Full project details nested for GET
    project_id = serializers.PrimaryKeyRelatedField( # For POST/PUT to link to a Project
        queryset=Project.objects.filter(is_published=True), # Only allow starting published projects
        source='project', write_only=True
    )
    user = BasicUserSerializerForProjects(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    submission_type_display = serializers.CharField(source='get_submission_type_display', read_only=True, allow_null=True)

    class Meta:
        model = UserProject
        fields = [
            'id', 'user', 'project', 'project_id', 
            'status', 'status_display',
            'started_at', 'submitted_at', 'completed_at',
            'submission_type', 'submission_type_display', 'submission_data_json',
            'assessment_score', 'assessment_feedback_html', 'ai_assessment_details_json',
            'last_accessed_at'
        ]
        read_only_fields = [
            'id', 'user', 'project', # project is read_only, project_id is write_only
            'status_display', 'submission_type_display',
            'started_at', 'submitted_at', 'completed_at',
            'assessment_score', 'assessment_feedback_html', 'ai_assessment_details_json',
            'last_accessed_at'
        ]
        # Writable fields by user action (via specific endpoints/logic):
        # 'status' (e.g., when starting/submitting - handled by view logic)
        # 'submission_type', 'submission_data_json' (on project submission)

class UserProjectStartSerializer(serializers.Serializer): # Used by UserProjectViewSet.start_project action
    project_id = serializers.UUIDField(required=True)

    def validate_project_id(self, value):
        if not Project.objects.filter(id=value, is_published=True).exists():
            raise serializers.ValidationError(_("Project not found or is not available to start."))
        return value

class UserProjectSubmitSerializer(serializers.Serializer): # Used by UserProjectViewSet.submit_project action
    submission_type = serializers.ChoiceField(choices=UserProject.SUBMISSION_TYPE_CHOICES, required=True)
    submission_content = serializers.CharField(required=False, allow_blank=True, help_text=_("For 'text_input' or direct code snippets if small."))
    repository_url = serializers.URLField(required=False, allow_blank=True, help_text=_("For 'repo_url' submission type."))
    # For 'json_data' (e.g. file contents) or 'gcs_link', the structure can be more complex
    # submission_data_json can capture these directly if passed as a JSON object.
    submission_files_json = serializers.JSONField(required=False, help_text=_("For 'json_data' type: {'filename.py': 'code...', ...}"))
    gcs_link = serializers.URLField(required=False, allow_blank=True, help_text=_("For 'gcs_link' submission type."))


    def validate(self, data):
        submission_type = data.get('submission_type')
        submission_content = data.get('submission_content')
        repository_url = data.get('repository_url')
        submission_files_json = data.get('submission_files_json')
        gcs_link = data.get('gcs_link')

        if submission_type == 'repo_url' and not repository_url:
            raise serializers.ValidationError({'repository_url': _("Repository URL is required for this submission type.")})
        elif submission_type == 'text_input' and not submission_content: # Allow empty string but not None
            if submission_content is None:
                 raise serializers.ValidationError({'submission_content': _("Content is required for text input submission.")})
        elif submission_type == 'json_data' and not submission_files_json:
            raise serializers.ValidationError({'submission_files_json': _("File data (JSON) is required for this submission type.")})
        elif submission_type == 'gcs_link' and not gcs_link:
            raise serializers.ValidationError({'gcs_link': _("GCS link is required for this submission type.")})
        
        # Ensure only relevant fields are provided for the submission type
        if submission_type != 'repo_url' and repository_url:
            raise serializers.ValidationError(_("Repository URL should only be provided for 'repo_url' submission type."))
        if submission_type != 'text_input' and submission_content:
            raise serializers.ValidationError(_("Submission content should only be provided for 'text_input' submission type."))
        # Add similar checks for submission_files_json and gcs_link

        return data
