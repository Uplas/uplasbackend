from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.conf import settings # For settings.AUTH_USER_MODEL

from .models import (
    CourseCategory, Course, Module, Topic, Quiz, Question, AnswerOption,
    UserCourseEnrollment, UserTopicAttempt, Review
)
# Assuming UserSerializer is in apps.users.serializers
# We need a basic version for instructor/user details to avoid circular imports if UserSerializer imports course-related things.
# A common practice is to have a "Lite" or "Basic" UserSerializer for such nested cases.
# For now, we'll define a simple one here or rely on __str__ if UserSerializer is too complex.

# A simplified UserSerializer for embedding, to avoid circular dependencies
class BasicUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'full_name', 'profile_picture_url'] # Add other essential fields for display
        read_only_fields = fields


class CourseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseCategory
        fields = ['id', 'name', 'slug', 'description', 'icon_url', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at']

class AnswerOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerOption
        # For students taking a quiz, 'is_correct' should not be sent.
        # It's included here for quiz creation/authoring and for showing results post-submission.
        fields = ['id', 'text', 'is_correct']
        read_only_fields = ['id']
        extra_kwargs = {
            'is_correct': {'write_only': False} # Default, but explicit
        }

class AnswerOptionStudentViewSerializer(serializers.ModelSerializer): # For students taking quiz
    class Meta:
        model = AnswerOption
        fields = ['id', 'text'] # Never show 'is_correct' to student during quiz
        read_only_fields = fields


class QuestionSerializer(serializers.ModelSerializer):
    # Dynamically switch option serializer based on context (viewing quiz vs. taking quiz)
    options = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ['id', 'quiz', 'text', 'question_type', 'order', 'explanation', 'points', 'options']
        read_only_fields = ['id']
        extra_kwargs = {
            'quiz': {'write_only': True, 'required': False}, # Quiz is context, not part of payload usually
            'explanation': {'read_only': True} # Explanation shown after attempt
        }

    def get_options(self, obj: Question):
        request = self.context.get('request')
        # Contextual serialization: if 'student_view' is in context, use student serializer for options
        if request and self.context.get('student_view', False):
            return AnswerOptionStudentViewSerializer(obj.options.all(), many=True, context=self.context).data
        return AnswerOptionSerializer(obj.options.all(), many=True, context=self.context).data


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True) # For displaying quizzes with questions

    class Meta:
        model = Quiz
        fields = ['id', 'topic', 'title', 'description', 'pass_mark_percentage', 'time_limit_minutes', 'questions']
        read_only_fields = ['id']
        extra_kwargs = {
            'topic': {'write_only': True, 'required': False}
        }

class TopicSerializer(serializers.ModelSerializer):
    quiz_details = QuizSerializer(read_only=True, required=False)
    user_progress = serializers.SerializerMethodField(read_only=True) # Renamed for clarity
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)


    class Meta:
        model = Topic
        fields = [
            'id', 'module', 'title', 'slug', 'order', 'content_type', 'content_type_display',
            'text_content_html', 'video_url', 'external_resource_url',
            'estimated_duration_minutes', 'is_previewable',
            'supports_ai_tutor', 'supports_tts', 'supports_ttv',
            'created_at', 'updated_at', 'quiz_details', 'user_progress'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at', 'quiz_details', 'content_type_display']
        extra_kwargs = {
            'module': {'write_only': True, 'required': False}
        }
    
    def get_user_progress(self, obj: Topic) -> dict | None:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            # Attempt to get enrollment from context if passed by the view for efficiency
            enrollment = self.context.get(f'enrollment_course_{obj.module.course_id}')
            if not enrollment: # Fallback to query if not in context (less efficient for lists)
                 try:
                    enrollment = UserCourseEnrollment.objects.get(user=user, course=obj.module.course)
                 except UserCourseEnrollment.DoesNotExist:
                    return None # User not enrolled in the course of this topic
            
            if enrollment:
                attempt = UserTopicAttempt.objects.filter(enrollment=enrollment, topic=obj).first()
                if attempt:
                    # Avoid circular import by using UserTopicAttemptSerializer name directly if it's defined later
                    # or create a BasicUserTopicAttemptSerializer
                    return BasicUserTopicAttemptSerializer(attempt, context=self.context).data
        return None


class ModuleSerializer(serializers.ModelSerializer):
    topics = TopicSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = ['id', 'course', 'title', 'description', 'order', 'created_at', 'updated_at', 'topics']
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'course': {'write_only': True, 'required': False}
        }

class CourseSerializer(serializers.ModelSerializer): # For listing courses
    category = CourseCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=CourseCategory.objects.all(), source='category', write_only=True, allow_null=True, required=False
    )
    instructor = BasicUserSerializer(read_only=True)
    instructor_id = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(), # TODO: Filter for actual instructors if applicable
        source='instructor', write_only=True, allow_null=True, required=False
    )
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)
    
    # User-specific data (can be annotated in view for performance)
    is_enrolled = serializers.SerializerMethodField()
    enrollment_progress = serializers.SerializerMethodField() # Percentage

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'subtitle', 'description_html', # Keep description for list previews if needed
            'category', 'category_id', 'instructor', 'instructor_id',
            'price', 'currency', 'cover_image_url', 'promo_video_url',
            'difficulty_level', 'difficulty_level_display', 'estimated_duration',
            'learning_objectives', 'requirements', 'target_audience', # Potentially exclude large fields from list view
            'is_published', 'published_date',
            'average_rating', 'total_enrollments',
            'created_at', 'updated_at',
            'is_enrolled', 'enrollment_progress'
        ]
        read_only_fields = [
            'id', 'slug', 'published_date', 'average_rating', 'total_enrollments',
            'created_at', 'updated_at', 'is_enrolled', 'enrollment_progress',
            'difficulty_level_display', 'instructor' # instructor is read-only as BasicUserSerializer
        ]
        # For admin/instructor creating course, make relevant fields writable
        # For list views, consider a "Lite" version excluding large text fields like description_html

    def get_is_enrolled(self, obj: Course) -> bool:
        # Efficient way: Check for annotated field from the viewset's get_queryset
        if hasattr(obj, 'is_enrolled_annotated'):
            return obj.is_enrolled_annotated
        
        # Fallback if not annotated (less efficient for lists)
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return UserCourseEnrollment.objects.filter(user=user, course=obj).exists()
        return False

    def get_enrollment_progress(self, obj: Course) -> int | None:
        # Efficient way: Check for annotated field
        if hasattr(obj, 'current_user_progress_annotated'):
            return obj.current_user_progress_annotated
            
        user = self.context.get('request').user
        if user and user.is_authenticated:
            try:
                # Try to get enrollment from context if pre-fetched by view for efficiency
                enrollment = self.context.get(f'enrollment_course_{obj.id}')
                if enrollment:
                    return enrollment.progress_percentage
                # Fallback query
                enrollment = UserCourseEnrollment.objects.get(user=user, course=obj)
                return enrollment.progress_percentage
            except UserCourseEnrollment.DoesNotExist:
                return None
        return None

class CourseDetailSerializer(CourseSerializer):
    modules = ModuleSerializer(many=True, read_only=True)

    class Meta(CourseSerializer.Meta): # Inherit fields from CourseSerializer
        fields = CourseSerializer.Meta.fields + ['modules']
        # For detail view, ensure all relevant fields are included
        # Example: 'description_html', 'learning_objectives', etc. should definitely be here.


class ReviewSerializer(serializers.ModelSerializer):
    user = BasicUserSerializer(read_only=True)
    # For write operations, user will be taken from request context.
    # course_id is typically from URL context.
    
    class Meta:
        model = Review
        fields = ['id', 'course', 'user', 'rating', 'comment', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'course', 'created_at', 'updated_at'] # 'course' usually set by view

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate(self, data):
        request = self.context.get('request')
        user = request.user if request else None
        
        # Course is typically set by the view from URL kwargs, not in payload
        # If it were in payload:
        # course = data.get('course') or (self.instance.course if self.instance else None)
        
        # For this serializer, we assume course context is handled by the view that uses it.
        # Here, we're mainly concerned with preventing duplicate reviews by the same user for the same course.
        # This check is more robustly handled at the view level or by database unique_together constraint.
        # If creating (self.instance is None):
        #   if course and user and Review.objects.filter(course=course, user=user).exists():
        #       raise serializers.ValidationError("You have already reviewed this course.")
        return data


class UserCourseEnrollmentSerializer(serializers.ModelSerializer):
    # Use a simpler CourseSerializer for nested course to avoid too much data/circularity
    class NestedCourseSerializer(serializers.ModelSerializer):
        instructor = BasicUserSerializer(read_only=True)
        category = CourseCategorySerializer(read_only=True)
        class Meta:
            model = Course
            fields = ['id', 'title', 'slug', 'cover_image_url', 'instructor', 'category', 'estimated_duration']
            read_only_fields = fields

    course = NestedCourseSerializer(read_only=True)
    user = BasicUserSerializer(read_only=True)
    
    # Simpler Topic Serializer for last_accessed_topic
    class NestedTopicSerializer(serializers.ModelSerializer):
        module_id = serializers.UUIDField(source='module.id', read_only=True)
        class Meta:
            model = Topic
            fields = ['id', 'title', 'slug', 'module_id', 'order', 'content_type']
            read_only_fields = fields
            
    last_accessed_topic = NestedTopicSerializer(read_only=True)

    class Meta:
        model = UserCourseEnrollment
        fields = [
            'id', 'user', 'course', 'enrolled_at', 'completed_at',
            'progress_percentage', 'last_accessed_topic'
        ]
        read_only_fields = fields # Enrollments are typically created by actions, not direct serialization


class BasicUserTopicAttemptSerializer(serializers.ModelSerializer): # For nesting in TopicSerializer
    class Meta:
        model = UserTopicAttempt
        fields = ['id', 'is_completed', 'completed_at', 'score', 'passed', 'last_accessed_at']
        read_only_fields = fields

class UserTopicAttemptSerializer(serializers.ModelSerializer): # Full serializer for individual attempt views
    topic = TopicSerializer(read_only=True, fields=['id', 'title', 'slug', 'content_type'])
    user = BasicUserSerializer(read_only=True)
    enrollment_id = serializers.UUIDField(source='enrollment.id', read_only=True)


    class Meta:
        model = UserTopicAttempt
        fields = [
            'id', 'enrollment_id', 'topic', 'user',
            'started_at', 'completed_at', 'is_completed',
            'score', 'passed', 'answer_history_json', 'last_accessed_at'
        ]
        read_only_fields = [
            'id', 'enrollment_id', 'topic', 'user', 'started_at',
            'last_accessed_at', 'answer_history_json', # answer_history populated by quiz submission logic
            'score', 'passed', 'completed_at', 'is_completed' # These are updated by system actions
        ]

# Serializers for Quiz Taking / Submission
class SubmitAnswerSerializer(serializers.Serializer):
    question_id = serializers.UUIDField(required=True)
    answer_option_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True # Allow empty list for deselection or if no options chosen for MC
    )
    text_answer = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_question_id(self, value):
        if not Question.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid question ID.")
        return value
    
    def validate(selfs, data):
        # Further validation based on question_type can be done in the view
        # or by fetching the question here if performance allows.
        # For example, ensure answer_option_ids are provided for choice questions.
        question_id = data.get('question_id')
        question = Question.objects.filter(id=question_id).first() # Avoids DoesNotExist if validated above
        
        if question:
            if question.question_type in ['multiple_choice', 'single_choice', 'true_false']:
                if data.get('answer_option_ids') is None: # Check for key presence
                    raise serializers.ValidationError({"answer_option_ids": "This field is required for choice questions."})
            elif question.question_type == 'short_answer':
                if data.get('text_answer') is None: # Check for key presence
                    raise serializers.ValidationError({"text_answer": "This field is required for short answer questions."})
        return data


class QuizSubmissionSerializer(serializers.Serializer):
    # topic_id is usually part of the URL, so not needed in serializer if view handles it.
    # If it were needed:
    # topic_id = serializers.UUIDField(required=True)
    answers = SubmitAnswerSerializer(many=True, required=True, allow_empty=False) # Must submit at least one answer attempt

    # def validate_topic_id(self, value): # If topic_id were in serializer
    #     try:
    #         topic = Topic.objects.get(id=value, content_type='quiz')
    #         if not hasattr(topic, 'quiz_details'):
    #              raise serializers.ValidationError("This topic does not have an associated quiz.")
    #     except Topic.DoesNotExist:
    #         raise serializers.ValidationError("Invalid topic ID or topic is not a quiz.")
    #     return value
