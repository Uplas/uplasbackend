from rest_framework import serializers
from .models import (
    CourseCategory, Course, Module, Topic, Quiz, Question, AnswerOption,
    UserCourseEnrollment, UserTopicAttempt, Review
)
from apps.users.serializers import UserSerializer # For instructor details

class CourseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseCategory
        fields = ['id', 'name', 'slug', 'description', 'icon_url', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at']

class AnswerOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerOption
        fields = ['id', 'text', 'is_correct'] # is_correct only for quiz authoring/results
        read_only_fields = ['id']

class QuestionSerializer(serializers.ModelSerializer):
    options = AnswerOptionSerializer(many=True, read_only=True) # For displaying questions
    # For creating/updating questions with options, a writable nested serializer might be needed
    # or options created/updated in the view.

    class Meta:
        model = Question
        fields = ['id', 'quiz', 'text', 'question_type', 'order', 'explanation', 'points', 'options']
        read_only_fields = ['id']
        extra_kwargs = {
            'quiz': {'write_only': True} # Quiz is context, not usually part of payload when creating question for a quiz
        }
class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True) # For displaying quizzes with questions

    class Meta:
        model = Quiz
        fields = ['id', 'topic', 'title', 'description', 'pass_mark_percentage', 'time_limit_minutes', 'questions']
        read_only_fields = ['id']
        extra_kwargs = {
            'topic': {'write_only': True} # Topic is context
        }

class TopicSerializer(serializers.ModelSerializer):
    # content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    quiz_details = QuizSerializer(read_only=True, required=False) # For topics of type 'quiz'
    # Progress for current user (will be added via serializer method field or annotation in view)
    user_progress = serializers.SerializerMethodField(read_only=True)


    class Meta:
        model = Topic
        fields = [
            'id', 'module', 'title', 'slug', 'order', 'content_type', # 'content_type_display',
            'text_content_html', 'video_url', 'external_resource_url', # 'quiz_data_json', 'assignment_details_html',
            'estimated_duration_minutes', 'is_previewable',
            'supports_ai_tutor', 'supports_tts', 'supports_ttv',
            'created_at', 'updated_at', 'quiz_details', 'user_progress'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at', 'quiz_details']
        extra_kwargs = {
            'module': {'write_only': True} # Module is usually context when creating/listing topics for a module
        }
    
    def get_user_progress(self, obj: Topic) -> dict | None:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            try:
                # Assuming UserCourseEnrollment is passed in context or fetched efficiently
                # This might require optimizing how enrollment is fetched/passed to avoid N+1
                enrollment = UserCourseEnrollment.objects.filter(user=user, course=obj.module.course).first()
                if enrollment:
                    attempt = UserTopicAttempt.objects.filter(enrollment=enrollment, topic=obj).first()
                    if attempt:
                        return UserTopicAttemptSerializer(attempt, context=self.context).data
            except UserCourseEnrollment.DoesNotExist:
                pass # User not enrolled
            except Exception as e: # Catch other potential errors
                print(f"Error in get_user_progress for topic {obj.id}: {e}")
        return None


class ModuleSerializer(serializers.ModelSerializer):
    topics = TopicSerializer(many=True, read_only=True) # Nested topics

    class Meta:
        model = Module
        fields = ['id', 'course', 'title', 'description', 'order', 'created_at', 'updated_at', 'topics']
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'course': {'write_only': True} # Course is usually context
        }

class CourseSerializer(serializers.ModelSerializer): # For listing and general info
    category = CourseCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=CourseCategory.objects.all(), source='category', write_only=True, allow_null=True, required=False
    )
    instructor = UserSerializer(read_only=True) # Display instructor details
    instructor_id = serializers.PrimaryKeyRelatedField(
        queryset=settings.AUTH_USER_MODEL.objects.all(), # Adjust if instructors are a subset of users
        source='instructor', write_only=True, allow_null=True, required=False
    )
    # difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)
    # For detailed view, modules might be included, or fetched separately
    # modules = ModuleSerializer(many=True, read_only=True) # Optional: include for detail view

    # User-specific data
    is_enrolled = serializers.SerializerMethodField()
    enrollment_progress = serializers.SerializerMethodField()


    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'subtitle', 'description_html',
            'category', 'category_id', 'instructor', 'instructor_id',
            'price', 'currency', 'cover_image_url', 'promo_video_url',
            'difficulty_level', # 'difficulty_level_display',
            'estimated_duration',
            'learning_objectives', 'requirements', 'target_audience',
            'is_published', 'published_date',
            'average_rating', 'total_enrollments',
            'created_at', 'updated_at',
            'is_enrolled', 'enrollment_progress'
            # 'modules' # Add if modules should be nested in general course GET
        ]
        read_only_fields = [
            'id', 'slug', 'published_date', 'average_rating', 'total_enrollments',
            'created_at', 'updated_at', 'is_enrolled', 'enrollment_progress'
        ]

    def get_is_enrolled(self, obj: Course) -> bool:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return UserCourseEnrollment.objects.filter(user=user, course=obj).exists()
        return False

    def get_enrollment_progress(self, obj: Course) -> int | None:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            try:
                enrollment = UserCourseEnrollment.objects.get(user=user, course=obj)
                return enrollment.progress_percentage
            except UserCourseEnrollment.DoesNotExist:
                return None
        return None


class CourseDetailSerializer(CourseSerializer): # Extends CourseSerializer for detailed view
    modules = ModuleSerializer(many=True, read_only=True) # Include modules with their topics

    class Meta(CourseSerializer.Meta):
        fields = CourseSerializer.Meta.fields + ['modules']


class ReviewSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True, fields=['id', 'username', 'full_name', 'profile_picture_url']) # Basic user info
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=settings.AUTH_USER_MODEL.objects.all(), source='user', write_only=True
    )
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(), source='course', write_only=True
    )

    class Meta:
        model = Review
        fields = ['id', 'course', 'course_id', 'user', 'user_id', 'rating', 'comment', 'created_at', 'updated_at']
        read_only_fields = ['id', 'course', 'user', 'created_at', 'updated_at']

    def validate(self, data):
        # User comes from request context, course from URL usually.
        # Ensure user hasn't already reviewed the course if creating.
        request_user = self.context.get('request').user
        course = data.get('course') or self.instance.course if self.instance else None

        if self.context['request'].method == 'POST': # On creation
            if not course:
                 raise serializers.ValidationError({"course_id": "Course is required to post a review."})
            if Review.objects.filter(course=course, user=request_user).exists():
                raise serializers.ValidationError(_("You have already reviewed this course."))
        return data


class UserCourseEnrollmentSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True, fields=[ # Basic course info for enrollment list
        'id', 'title', 'slug', 'cover_image_url', 'instructor', 'category'
    ]) 
    user = UserSerializer(read_only=True, fields=['id', 'username'])
    last_accessed_topic = TopicSerializer(read_only=True, fields=['id', 'title', 'slug', 'module'])


    class Meta:
        model = UserCourseEnrollment
        fields = [
            'id', 'user', 'course', 'enrolled_at', 'completed_at',
            'progress_percentage', 'last_accessed_topic'
        ]
        read_only_fields = ['id', 'user', 'course', 'enrolled_at', 'completed_at', 'progress_percentage', 'last_accessed_topic']

class UserTopicAttemptSerializer(serializers.ModelSerializer):
    topic = TopicSerializer(read_only=True, fields=['id', 'title', 'slug', 'content_type']) # Basic topic info
    # enrollment = UserCourseEnrollmentSerializer(read_only=True) # Could be too verbose, often enrollment is context

    class Meta:
        model = UserTopicAttempt
        fields = [
            'id', 'enrollment', 'topic', 'user', # user is mostly for consistency, already on enrollment
            'started_at', 'completed_at', 'is_completed',
            'score', 'passed', 'answer_history_json', 'last_accessed_at'
        ]
        read_only_fields = ['id', 'enrollment', 'topic', 'user', 'started_at', 'last_accessed_at']

# Serializers for Quiz Taking / Submission
class SubmitAnswerSerializer(serializers.Serializer):
    question_id = serializers.UUIDField(required=True)
    # For multiple_choice/single_choice, answer_option_ids would be a list of UUIDs or single UUID
    answer_option_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False, # Not required for short_answer
        allow_empty=True
    )
    # For short_answer
    text_answer = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        question_id = data.get('question_id')
        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            raise serializers.ValidationError({"question_id": "Invalid question ID."})

        if question.question_type in ['multiple_choice', 'single_choice']:
            if not data.get('answer_option_ids'):
                raise serializers.ValidationError({"answer_option_ids": "This field is required for multiple/single choice questions."})
            # Further validation: ensure option_ids belong to the question
            valid_option_ids = list(question.options.values_list('id', flat=True))
            for opt_id in data.get('answer_option_ids'):
                if opt_id not in valid_option_ids:
                    raise serializers.ValidationError({"answer_option_ids": f"Invalid option ID: {opt_id} for question {question_id}."})
            if question.question_type == 'single_choice' and len(data.get('answer_option_ids')) > 1:
                raise serializers.ValidationError({"answer_option_ids": "Only one option can be selected for a single choice question."})

        elif question.question_type == 'short_answer':
            if data.get('text_answer') is None : # Allow empty string, but key must be present if type is short_answer
                raise serializers.ValidationError({"text_answer": "This field is required for short answer questions."})
        elif question.question_type == 'true_false':
             if not data.get('answer_option_ids') or len(data.get('answer_option_ids')) != 1:
                raise serializers.ValidationError({"answer_option_ids": "One option (True or False) must be selected."})
            # Ensure the option is one of the True/False options for this question

        return data

class QuizSubmissionSerializer(serializers.Serializer):
    topic_id = serializers.UUIDField(required=True) # The topic that is a quiz
    answers = SubmitAnswerSerializer(many=True, required=True) # List of answers

    def validate_topic_id(self, value):
        try:
            topic = Topic.objects.get(id=value, content_type='quiz')
            if not hasattr(topic, 'quiz_details'):
                 raise serializers.ValidationError("This topic does not have an associated quiz.")
        except Topic.DoesNotExist:
            raise serializers.ValidationError("Invalid topic ID or topic is not a quiz.")
        return value
