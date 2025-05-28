from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.db import transaction # For atomic operations

from .models import (
    Category, Course, Module, Topic, Question, Choice,
    Enrollment, CourseReview, CourseProgress, TopicProgress,
    QuizAttempt, UserTopicAttemptAnswer
)
from django.contrib.auth import get_user_model
User = get_user_model()


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'icon_url']
        read_only_fields = ['id']

class SimpleUserSerializer(serializers.ModelSerializer): # Assuming this is used for instructor/user display
    class Meta:
        model = User
        # Ensure 'userprofile' is related_name from User to UserProfile if accessing avatar_url
        # For now, basic fields:
        fields = ['id', 'username', 'full_name', 'email', 'profile_picture_url']
        # If User model directly has profile_picture_url, otherwise adjust source
        # example: 'profile_picture_url': serializers.URLField(source='userprofile.avatar_url', read_only=True)

class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ['id', 'text', 'is_correct', 'order']
        read_only_fields = ['id']

class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(many=True, read_only=False) # Allow writing choices

    class Meta:
        model = Question
        fields = ['id', 'topic_id', 'text', 'question_type', 'order', 'explanation', 'choices']
        read_only_fields = ['id']
        extra_kwargs = {
            'topic_id': {'write_only': True, 'required': False, 'source': 'topic'}, # Made not required for updates
            'explanation': {'required': False, 'allow_blank': True, 'allow_null': True}
        }

    def create(self, validated_data):
        choices_data = validated_data.pop('choices', [])
        # Topic is expected to be set in the view if creating questions under a topic
        question = Question.objects.create(**validated_data)
        for choice_data in choices_data:
            Choice.objects.create(question=question, **choice_data)
        return question

    def update(self, instance, validated_data):
        choices_data = validated_data.pop('choices', None)
        
        # Update Question fields
        instance.text = validated_data.get('text', instance.text)
        instance.question_type = validated_data.get('question_type', instance.question_type)
        instance.order = validated_data.get('order', instance.order)
        instance.explanation = validated_data.get('explanation', instance.explanation)
        # instance.topic = validated_data.get('topic', instance.topic) # Topic change not typical here
        instance.save()

        if choices_data is not None:
            # Simpler strategy: Delete existing choices and create new ones.
            # For more complex scenarios, a granular update (match by ID, update/create/delete) is better.
            instance.choices.all().delete()
            for choice_data in choices_data:
                Choice.objects.create(question=instance, **choice_data)
        
        return instance


class TopicListSerializer(serializers.ModelSerializer):
    module_title = serializers.CharField(source='module.title', read_only=True)
    course_id = serializers.UUIDField(source='module.course.id', read_only=True)
    is_completed_by_user = serializers.SerializerMethodField()


    class Meta:
        model = Topic
        fields = [
            'id', 'title', 'slug', 'order', 'estimated_duration_minutes',
            'is_previewable', 'module_id', 'module_title', 'course_id',
            'is_completed_by_user'
        ]
    
    def get_is_completed_by_user(self, obj):
        user = self.context['request'].user
        if user and user.is_authenticated:
            return TopicProgress.objects.filter(user=user, topic=obj, is_completed=True).exists()
        return False

class TopicDetailSerializer(serializers.ModelSerializer):
    module_title = serializers.CharField(source='module.title', read_only=True)
    course_id = serializers.UUIDField(source='module.course.id', read_only=True)
    questions = QuestionSerializer(many=True, read_only=True) # Questions are typically managed via their own endpoint or nested POST
    
    supports_ai_tutor_resolved = serializers.SerializerMethodField(method_name='get_supports_ai_tutor')
    supports_tts_resolved = serializers.SerializerMethodField(method_name='get_supports_tts')
    supports_ttv_resolved = serializers.SerializerMethodField(method_name='get_supports_ttv')
    is_completed_by_user = serializers.SerializerMethodField()


    class Meta:
        model = Topic
        fields = [
            'id', 'title', 'slug', 'content', 'order', 'estimated_duration_minutes',
            'is_previewable', 'module_id', 'module_title', 'course_id', 'questions',
            'supports_ai_tutor', 'supports_tts', 'supports_ttv', # Raw values
            'supports_ai_tutor_resolved', 'supports_tts_resolved', 'supports_ttv_resolved', # Resolved values
            'is_completed_by_user',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'questions',
                            'supports_ai_tutor_resolved', 'supports_tts_resolved', 'supports_ttv_resolved',
                            'is_completed_by_user']
        extra_kwargs = {
            'module_id': {'write_only': True, 'required': False, 'source': 'module'}, # Required on create, not on update usually
            'supports_ai_tutor': {'allow_null': True}, # Allow explicit null to inherit
            'supports_tts': {'allow_null': True},
            'supports_ttv': {'allow_null': True},
        }
    
    def validate_content(self, value):
        """
        Validates the schema for the Topic.content JSONField.
        Example schema from model:
        {
          "type": "text" | "video" | "quiz" | "external_resource" | "code_interactive",
          "text_content": "Markdown or HTML for text type",
          "video_url": "URL for video type",
          "video_provider": "youtube", // "vimeo", "custom"
          "resource_url": "URL for external resource type",
          "code_language": "python",
          "initial_code": "print('Hello')",
          "solution_code": "print('Hello, World!')"
          // For quiz, questions are linked via the Question model.
        }
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError(_("Content must be a JSON object."))
        
        content_type = value.get('type')
        if not content_type:
            raise serializers.ValidationError(_("Content object must have a 'type' field."))
        
        allowed_types = ["text", "video", "quiz", "external_resource", "code_interactive"]
        if content_type not in allowed_types:
            raise serializers.ValidationError(
                _(f"Invalid content type '{content_type}'. Allowed types are: {', '.join(allowed_types)}.")
            )

        if content_type == "text" and "text_content" not in value: # Check for presence, not just truthiness
            raise serializers.ValidationError(_("Text content must have a 'text_content' field."))
        if content_type == "video" and "video_url" not in value:
            raise serializers.ValidationError(_("Video content must have a 'video_url' field."))
        if content_type == "external_resource" and "resource_url" not in value:
            raise serializers.ValidationError(_("External resource content must have a 'resource_url' field."))
        if content_type == "code_interactive":
            if "code_language" not in value or "initial_code" not in value:
                raise serializers.ValidationError(
                    _("Code interactive content must have 'code_language' and 'initial_code' fields.")
                )
        # For 'quiz' type, no specific 'content' fields are mandated here, as questions are linked separately.
        # You might add a check to ensure 'quiz_id' is not present if you don't use it.
        return value

    def get_supports_ai_tutor(self, obj):
        return obj.get_supports_ai_tutor()

    def get_supports_tts(self, obj):
        return obj.get_supports_tts()

    def get_supports_ttv(self, obj):
        return obj.get_supports_ttv()

    def get_is_completed_by_user(self, obj):
        user = self.context['request'].user
        if user and user.is_authenticated:
            if hasattr(obj, 'user_topic_progress_for_topic'): # Check if prefetched
                 return any(tp.is_completed for tp in obj.user_topic_progress_for_topic)
            return TopicProgress.objects.filter(user=user, topic=obj, is_completed=True).exists()
        return False

class TopicProgressSerializer(serializers.ModelSerializer):
    topic_title = serializers.CharField(source='topic.title', read_only=True)
    topic_slug = serializers.CharField(source='topic.slug', read_only=True)
    module_id = serializers.UUIDField(source='topic.module.id', read_only=True)
    course_id = serializers.UUIDField(source='topic.module.course.id', read_only=True)

    class Meta:
        model = TopicProgress
        fields = ['id', 'user_id', 'topic_id', 'topic_title', 'topic_slug', 'module_id', 'course_id',
                  'is_completed', 'completed_at']
        read_only_fields = ['id', 'user_id', 'topic_title', 'topic_slug', 'module_id', 'course_id', 'completed_at']
        # is_completed is writable for marking as complete.

class ModuleListSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_slug = serializers.CharField(source='course.slug', read_only=True)

    class Meta:
        model = Module
        fields = ['id', 'title', 'order', 'description', 'course_id', 'course_title', 'course_slug']

class ModuleDetailSerializer(serializers.ModelSerializer):
    # Topics are fetched with completion status for the current user
    topics = TopicListSerializer(many=True, read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_slug = serializers.CharField(source='course.slug', read_only=True)
    user_progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            'id', 'title', 'order', 'description', 'topics',
            'course_id', 'course_title', 'course_slug', 'user_progress_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'topics', 'user_progress_percentage']
        extra_kwargs = {
            'course_id': {'write_only': True, 'required': False, 'source': 'course'}, # Req on create, not update
        }

    def get_user_progress_percentage(self, obj):
        user = self.context['request'].user
        if user and user.is_authenticated:
            # This relies on `TopicListSerializer.get_is_completed_by_user`
            # and `topics` being correctly populated (e.g., via prefetch in view)
            completed_count = 0
            total_topics = 0
            for topic_data in self.fields['topics'].to_representation(obj.topics.all()): # Use serializer's representation
                total_topics +=1
                if topic_data.get('is_completed_by_user', False):
                    completed_count +=1
            
            if total_topics == 0:
                return 0.0
            return (completed_count / total_topics) * 100
        return 0.0


class CourseReviewSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True) # Display user details
    # user_id is not needed for write as user is from request context
    # course_id is also typically from URL context in a nested ViewSet, not direct payload

    class Meta:
        model = CourseReview
        fields = ['id', 'user', 'course', 'rating', 'comment', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'course', 'created_at', 'updated_at']
        # Writable: rating, comment

    def validate(self, data):
        request = self.context.get('request')
        user = request.user
        
        # `course` instance is expected to be set by the view before validation, or passed in initial_data
        # For create, course comes from URL typically. For update, from instance.
        course = self.instance.course if self.instance else self.context.get('course_instance')

        if not course: # Should be caught by view if course_instance not provided for create
            raise serializers.ValidationError(_("Course context is missing for review validation."))

        if self.instance: # Updating existing review
            if self.instance.user != user and not user.is_staff:
                raise serializers.ValidationError(_("You can only edit your own reviews."))
        else: # Creating a new review
            if not Enrollment.objects.filter(user=user, course=course).exists():
                 raise serializers.ValidationError(_("You must be enrolled in this course to submit a review."))
            if CourseReview.objects.filter(user=user, course=course).exists():
                raise serializers.ValidationError(_("You have already reviewed this course."))
        return data


class CourseListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    instructor_info = SimpleUserSerializer(source='instructor', read_only=True) # Nested instructor details
    is_enrolled = serializers.SerializerMethodField() # Or use annotated field from queryset

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'short_description', 'thumbnail_url', 'price', 'currency',
            'level', 'language', 'average_rating', 'total_reviews', 'total_enrollments',
            'category_id', 'category_name', 'instructor_info', 'is_free',
            'is_featured', 'is_enrolled', 'total_duration_minutes'
        ]

    def get_is_enrolled(self, obj):
        # Relies on annotation _user_is_enrolled from ViewSet's get_queryset
        if hasattr(obj, '_user_is_enrolled'):
            return obj._user_is_enrolled
        
        # Fallback if annotation not present (less efficient for lists)
        user = self.context['request'].user
        if user and user.is_authenticated:
            return Enrollment.objects.filter(user=user, course=obj).exists()
        return False

class CourseDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    instructor = SimpleUserSerializer(read_only=True)
    # Use context in ModuleDetailSerializer to pass request for user progress
    modules = serializers.SerializerMethodField()
    reviews = CourseReviewSerializer(many=True, read_only=True, source='reviews') # Ensure 'reviews' is prefetched
    
    is_enrolled = serializers.SerializerMethodField()
    user_progress_percentage = serializers.SerializerMethodField()
    last_accessed_topic_slug = serializers.SerializerMethodField() # Changed from ID to slug for frontend

    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False, allow_null=True
    )
    # instructor_id is not typically changed by users after creation; handled by admin or initial creation logic

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'short_description', 'long_description', 'thumbnail_url',
            'promo_video_url', 'price', 'currency', 'level', 'language', 'is_published', 'is_free',
            'average_rating', 'total_reviews', 'total_enrollments', 'total_duration_minutes',
            'supports_ai_tutor', 'supports_tts', 'supports_ttv',
            'category', 'category_id', 'instructor', 'modules', 'reviews',
            'is_enrolled', 'user_progress_percentage', 'last_accessed_topic_slug',
            'created_at', 'updated_at', 'published_at'
        ]
        read_only_fields = [
            'id', 'average_rating', 'total_reviews', 'total_enrollments', 'total_duration_minutes',
            'created_at', 'updated_at', 'published_at', 'instructor', 'category', 'reviews',
            'is_enrolled', 'user_progress_percentage', 'last_accessed_topic_slug'
        ]
        extra_kwargs = {
            'long_description': {'required': False, 'allow_blank': True, 'allow_null': True},
            'thumbnail_url': {'required': False, 'allow_blank': True, 'allow_null': True},
            'promo_video_url': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def get_modules(self, obj):
        # Pass context (like request) to ModuleDetailSerializer if it needs it
        return ModuleDetailSerializer(obj.modules.all(), many=True, context=self.context).data

    def get_is_enrolled(self, obj):
        if hasattr(obj, '_user_is_enrolled'):
            return obj._user_is_enrolled
        user = self.context['request'].user
        if user and user.is_authenticated:
            return Enrollment.objects.filter(user=user, course=obj).exists()
        return False

    def get_user_progress_percentage(self, obj):
        if hasattr(obj, '_user_progress_percentage'):
            return obj._user_progress_percentage
        user = self.context['request'].user
        if user and user.is_authenticated:
            progress = CourseProgress.objects.filter(user=user, course=obj).first()
            return progress.progress_percentage if progress else 0.0
        return 0.0
    
    def get_last_accessed_topic_slug(self, obj):
        if hasattr(obj, '_user_last_accessed_topic_id'): # Assuming view annotates with ID
            topic_id = obj._user_last_accessed_topic_id
            if topic_id:
                try:
                    return Topic.objects.get(pk=topic_id).slug
                except Topic.DoesNotExist:
                    return None
            return None

        user = self.context['request'].user
        if user and user.is_authenticated:
            progress = CourseProgress.objects.select_related('last_accessed_topic').filter(user=user, course=obj).first()
            return progress.last_accessed_topic.slug if progress and progress.last_accessed_topic else None
        return None

    def create(self, validated_data):
        # Instructor is set in the view's perform_create
        if 'instructor' not in validated_data and self.context.get('request'):
             validated_data['instructor'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Prevent changing instructor unless admin
        if 'instructor' in validated_data and not self.context['request'].user.is_staff:
            validated_data.pop('instructor')
        return super().update(instance, validated_data)


class EnrollmentSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_slug = serializers.CharField(source='course.slug', read_only=True)

    # These fields are for write operations if creating enrollment directly via this serializer
    # However, enrollment is often a result of an action (e.g., CourseViewSet.enroll)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True, required=False
    )
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.filter(is_published=True), source='course', write_only=True
    )

    class Meta:
        model = Enrollment
        fields = ['id', 'user_id', 'course_id', 'user_email', 'course_title', 'course_slug', 'enrolled_at']
        read_only_fields = ['id', 'user_email', 'course_title', 'course_slug', 'enrolled_at']

    def validate(self, data):
        # User is derived from context in the view if not explicitly passed
        user = self.context['request'].user if 'request' in self.context else data.get('user')
        course = data.get('course') # This is a Course instance after PrimaryKeyRelatedField validation

        if not user:
            raise serializers.ValidationError(_("User context is missing."))
        if not course:
            raise serializers.ValidationError(_("Course is required for enrollment."))

        if Enrollment.objects.filter(user=user, course=course).exists():
            raise serializers.ValidationError(_("You are already enrolled in this course."))
        
        # Payment check should ideally happen in the view before calling this serializer
        # if it's a direct creation. The `enroll` action in CourseViewSet handles this.
        return data
    
    def create(self, validated_data):
        if 'user' not in validated_data and self.context.get('request'):
            validated_data['user'] = self.context['request'].user
        
        enrollment = super().create(validated_data)
        # Ensure CourseProgress is created
        CourseProgress.objects.get_or_create(
            user=enrollment.user,
            course=enrollment.course,
            defaults={'enrollment': enrollment} # Pass enrollment if your CourseProgress model links it
        )
        return enrollment

class CourseProgressDetailSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_slug = serializers.CharField(source='course.slug', read_only=True)
    topic_progress_entries = TopicProgressSerializer(many=True, read_only=True)
    last_accessed_topic = TopicListSerializer(read_only=True) # Display summary of last accessed topic

    class Meta:
        model = CourseProgress
        fields = [
            'id', 'user_email', 'course_title', 'course_slug', 'completed_topics_count',
            'total_topics_count', 'progress_percentage', 'completed_at',
            'last_accessed_topic', 'updated_at', 'topic_progress_entries'
        ]

class UserTopicAttemptAnswerSerializer(serializers.ModelSerializer):
    # These are for writing answers when submitting a quiz
    question_id = serializers.PrimaryKeyRelatedField(queryset=Question.objects.all(), source='question')
    selected_choice_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=Choice.objects.all()),
        write_only=True,
        required=False, # Not all question types have choices
        allow_empty=True # Allow submitting empty list if no choice selected (though might be invalid for some Q types)
    )
    # Add fields for other answer types if needed (e.g., text_answer for fill-in-the-blank)
