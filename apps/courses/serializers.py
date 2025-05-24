from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.db import transaction # For atomic operations

from .models import (
    Category, Course, Module, Topic, Question, Choice,
    Enrollment, CourseReview, CourseProgress, TopicProgress,
    QuizAttempt, UserTopicAttemptAnswer
)
# Import User model for instructor representation if not already available via settings
from django.contrib.auth import get_user_model
User = get_user_model()


# --- Basic Serializers (often used for choices or simple representations) ---
class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for the Category model.
    """
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'icon_url']
        read_only_fields = ['id']

class SimpleUserSerializer(serializers.ModelSerializer):
    """
    A simple serializer for user information, typically for instructor display.
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'email'] # Add other fields as needed, e.g., profile picture

# --- Choice and Question Serializers ---
class ChoiceSerializer(serializers.ModelSerializer):
    """
    Serializer for the Choice model (answers to questions).
    """
    class Meta:
        model = Choice
        fields = ['id', 'text', 'is_correct', 'order']
        read_only_fields = ['id']
        # For instructors creating quizzes, 'is_correct' should be writable.
        # For students taking quizzes, 'is_correct' should be hidden or read-only.

class QuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for the Question model. Includes choices.
    """
    choices = ChoiceSerializer(many=True, read_only=False) # Allow creating choices with questions

    class Meta:
        model = Question
        fields = ['id', 'topic_id', 'text', 'question_type', 'order', 'explanation', 'choices']
        read_only_fields = ['id']
        extra_kwargs = {
            'topic_id': {'write_only': True, 'required': True, 'source': 'topic'},
            'explanation': {'required': False, 'allow_blank': True, 'allow_null': True}
        }

    def create(self, validated_data):
        choices_data = validated_data.pop('choices', [])
        question = Question.objects.create(**validated_data)
        for choice_data in choices_data:
            Choice.objects.create(question=question, **choice_data)
        return question

    def update(self, instance, validated_data):
        choices_data = validated_data.pop('choices', None)
        
        # Update Question instance fields
        instance.text = validated_data.get('text', instance.text)
        instance.question_type = validated_data.get('question_type', instance.question_type)
        instance.order = validated_data.get('order', instance.order)
        instance.explanation = validated_data.get('explanation', instance.explanation)
        instance.save()

        if choices_data is not None:
            # Simple approach: delete existing and create new ones.
            # More complex logic can be added for partial updates if needed.
            instance.choices.all().delete()
            for choice_data in choices_data:
                Choice.objects.create(question=instance, **choice_data)
        
        return instance


# --- Topic Serializers ---
class TopicListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing Topics (less detail).
    """
    module_title = serializers.CharField(source='module.title', read_only=True)
    course_id = serializers.UUIDField(source='module.course.id', read_only=True)

    class Meta:
        model = Topic
        fields = [
            'id', 'title', 'slug', 'order', 'estimated_duration_minutes',
            'is_previewable', 'module_id', 'module_title', 'course_id'
        ]

class TopicDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed view of a Topic.
    Includes questions if the topic content indicates a quiz.
    """
    module_title = serializers.CharField(source='module.title', read_only=True)
    course_id = serializers.UUIDField(source='module.course.id', read_only=True)
    questions = QuestionSerializer(many=True, read_only=True) # Read-only here; manage questions separately
    supports_ai_tutor = serializers.SerializerMethodField()
    supports_tts = serializers.SerializerMethodField()
    supports_ttv = serializers.SerializerMethodField()
    is_completed_by_user = serializers.SerializerMethodField()

    class Meta:
        model = Topic
        fields = [
            'id', 'title', 'slug', 'content', 'order', 'estimated_duration_minutes',
            'is_previewable', 'module_id', 'module_title', 'course_id', 'questions',
            'supports_ai_tutor', 'supports_tts', 'supports_ttv', 'is_completed_by_user',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'questions']

    def get_supports_ai_tutor(self, obj):
        return obj.get_supports_ai_tutor()

    def get_supports_tts(self, obj):
        return obj.get_supports_tts()

    def get_supports_ttv(self, obj):
        return obj.get_supports_ttv()

    def get_is_completed_by_user(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return TopicProgress.objects.filter(user=user, topic=obj, is_completed=True).exists()
        return False

class TopicProgressSerializer(serializers.ModelSerializer):
    """
    Serializer for TopicProgress.
    """
    topic_title = serializers.CharField(source='topic.title', read_only=True)
    class Meta:
        model = TopicProgress
        fields = ['id', 'user_id', 'topic_id', 'topic_title', 'is_completed', 'completed_at']
        read_only_fields = ['id', 'user_id', 'topic_title', 'completed_at'] # User and topic set by view context

# --- Module Serializers ---
class ModuleListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing Modules (less detail).
    """
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Module
        fields = ['id', 'title', 'order', 'description', 'course_id', 'course_title']

class ModuleDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed view of a Module. Includes its topics.
    """
    topics = TopicListSerializer(many=True, read_only=True) # Use list serializer for topics here
    course_title = serializers.CharField(source='course.title', read_only=True)
    user_progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            'id', 'title', 'order', 'description', 'topics',
            'course_id', 'course_title', 'user_progress_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'topics']

    def get_user_progress_percentage(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            total_topics = obj.topics.count()
            if total_topics == 0:
                return 0.0
            completed_topics = TopicProgress.objects.filter(
                user=user,
                topic__module=obj,
                is_completed=True
            ).count()
            return (completed_topics / total_topics) * 100
        return 0.0


# --- Course Serializers ---
class CourseReviewSerializer(serializers.ModelSerializer):
    """
    Serializer for CourseReview.
    """
    user = SimpleUserSerializer(read_only=True) # Display user info on read
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True
    )
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(), source='course', write_only=True
    )

    class Meta:
        model = CourseReview
        fields = ['id', 'user', 'user_id', 'course_id', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']

    def validate(self, data):
        request = self.context.get('request')
        user = request.user if request else data.get('user') # For create, user from request.user
        course = data.get('course')

        if self.instance: # Update
            if self.instance.user != user and not user.is_staff:
                raise serializers.ValidationError(_("You can only edit your own reviews."))
        else: # Create
            if CourseReview.objects.filter(user=user, course=course).exists():
                raise serializers.ValidationError(_("You have already reviewed this course."))
            if not Enrollment.objects.filter(user=user, course=course).exists():
                 raise serializers.ValidationError(_("You must be enrolled in this course to submit a review."))
        return data

class CourseListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing Courses (summary view).
    """
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    instructor_name = serializers.CharField(source='instructor.get_full_name', read_only=True, allow_null=True) # Assumes User model has get_full_name
    is_enrolled = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'short_description', 'thumbnail_url', 'price', 'currency',
            'level', 'language', 'average_rating', 'total_reviews', 'total_enrollments',
            'category_id', 'category_name', 'instructor_id', 'instructor_name', 'is_free',
            'is_featured', 'is_enrolled', 'total_duration_minutes'
        ]

    def get_is_enrolled(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return Enrollment.objects.filter(user=user, course=obj).exists()
        return False

class CourseDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed view of a Course. Includes modules, reviews, etc.
    """
    category = CategorySerializer(read_only=True)
    instructor = SimpleUserSerializer(read_only=True)
    modules = ModuleDetailSerializer(many=True, read_only=True) # Use detailed module serializer
    reviews = CourseReviewSerializer(many=True, read_only=True, source='reviews') # Explicit source
    
    is_enrolled = serializers.SerializerMethodField()
    user_progress_percentage = serializers.SerializerMethodField()
    last_accessed_topic_id = serializers.SerializerMethodField()

    # Writable fields for related objects (used during course creation/update by instructor)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False, allow_null=True
    )
    # instructor_id is usually set automatically or based on request.user

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'short_description', 'long_description', 'thumbnail_url',
            'promo_video_url', 'price', 'currency', 'level', 'language', 'is_published', 'is_free',
            'average_rating', 'total_reviews', 'total_enrollments', 'total_duration_minutes',
            'supports_ai_tutor', 'supports_tts', 'supports_ttv',
            'category', 'category_id', 'instructor', 'modules', 'reviews',
            'is_enrolled', 'user_progress_percentage', 'last_accessed_topic_id',
            'created_at', 'updated_at', 'published_at'
        ]
        read_only_fields = [
            'id', 'average_rating', 'total_reviews', 'total_enrollments', 'total_duration_minutes',
            'created_at', 'updated_at', 'published_at', 'instructor', 'category', 'modules', 'reviews'
        ]
        extra_kwargs = {
            'long_description': {'required': False, 'allow_blank': True, 'allow_null': True},
            'thumbnail_url': {'required': False, 'allow_blank': True, 'allow_null': True},
            'promo_video_url': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def get_is_enrolled(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return Enrollment.objects.filter(user=user, course=obj).exists()
        return False

    def get_user_progress_percentage(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            progress = CourseProgress.objects.filter(user=user, course=obj).first()
            return progress.progress_percentage if progress else 0.0
        return 0.0
    
    def get_last_accessed_topic_id(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            progress = CourseProgress.objects.filter(user=user, course=obj).first()
            return progress.last_accessed_topic_id if progress and progress.last_accessed_topic_id else None
        return None

    def create(self, validated_data):
        # Instructor should be set from the request user in the view
        validated_data['instructor'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Ensure instructor cannot be changed by non-admin, or handle as per business logic
        if 'instructor' in validated_data and not self.context['request'].user.is_staff:
            validated_data.pop('instructor') # Prevent changing instructor unless admin
        return super().update(instance, validated_data)


# --- Enrollment and Progress Serializers ---
class EnrollmentSerializer(serializers.ModelSerializer):
    """
    Serializer for Enrollment.
    """
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True, required=False
    )
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(), source='course', write_only=True
    )
    user_email = serializers.EmailField(source='user.email', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Enrollment
        fields = ['id', 'user_id', 'course_id', 'user_email', 'course_title', 'enrolled_at']
        read_only_fields = ['id', 'user_email', 'course_title', 'enrolled_at']

    def validate(self, data):
        user = self.context['request'].user if 'request' in self.context else data.get('user')
        course = data.get('course')

        if Enrollment.objects.filter(user=user, course=course).exists():
            raise serializers.ValidationError(_("You are already enrolled in this course."))
        
        # Payment check should ideally happen in the view before creating enrollment for paid courses
        # For free courses, this serializer can proceed.
        if not course.is_free:
            # This is a simplified check. Real payment verification is more complex.
            # Consider a 'payment_successful' flag in context or a separate payment step.
            # For now, we assume the view handles payment for paid courses.
            pass
            
        return data
    
    def create(self, validated_data):
        # Set user from context if not provided (should always be from context for security)
        if 'user' not in validated_data and 'request' in self.context:
            validated_data['user'] = self.context['request'].user
        
        enrollment = super().create(validated_data)
        # Ensure CourseProgress is created upon enrollment
        CourseProgress.objects.get_or_create(
            user=enrollment.user,
            course=enrollment.course,
            defaults={'enrollment': enrollment}
        )
        return enrollment

class CourseProgressDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for CourseProgress.
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    topic_progress_entries = TopicProgressSerializer(many=True, read_only=True)
    last_accessed_topic = TopicListSerializer(read_only=True)

    class Meta:
        model = CourseProgress
        fields = [
            'id', 'user_email', 'course_title', 'completed_topics_count',
            'total_topics_count', 'progress_percentage', 'completed_at',
            'last_accessed_topic', 'updated_at', 'topic_progress_entries'
        ]


# --- Quiz Submission Serializers ---
class UserTopicAttemptAnswerSerializer(serializers.ModelSerializer):
    """
    Serializer for submitting an answer to a question.
    """
    question_id = serializers.PrimaryKeyRelatedField(queryset=Question.objects.all(), source='question')
    selected_choice_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=Choice.objects.all()),
        write_only=True,
        required=False # Not all question types have choices
    )

    class Meta:
        model = UserTopicAttemptAnswer
        fields = ['question_id', 'selected_choice_ids'] # Add 'answer_text' if other types are supported

class QuizSubmissionSerializer(serializers.Serializer): # Not a ModelSerializer
    """
    Serializer for submitting a full quiz attempt for a topic.
    """
    topic_id = serializers.UUIDField()
    answers = UserTopicAttemptAnswerSerializer(many=True) # List of answers

    def validate_topic_id(self, value):
        try:
            topic = Topic.objects.get(pk=value)
        except Topic.DoesNotExist:
            raise serializers.ValidationError(_("Invalid Topic ID."))
        
        # Check if user is enrolled
        user = self.context['request'].user
        if not Enrollment.objects.filter(user=user, course=topic.module.course).exists():
            # Allow instructors/staff to submit for testing purposes
            if not (user.is_staff or topic.module.course.instructor == user):
                 raise serializers.ValidationError(_("You must be enrolled in the course to submit this quiz."))
        return value

    def validate_answers(self, value):
        if not value:
            raise serializers.ValidationError(_("Answers list cannot be empty."))
        
        topic_id = self.initial_data.get('topic_id')
        question_ids_in_submission = {ans['question_id'].id for ans in value}
        
        try:
            topic = Topic.objects.get(pk=topic_id)
            questions_in_topic = Question.objects.filter(topic=topic)
            question_ids_in_topic = {q.id for q in questions_in_topic}

            if not question_ids_in_submission.issubset(question_ids_in_topic):
                raise serializers.ValidationError(_("One or more submitted question IDs do not belong to this topic."))

            # Optional: Check if all questions in the topic are answered
            # if len(question_ids_in_submission) != len(question_ids_in_topic):
            #     raise serializers.ValidationError(_("Not all questions for this topic were answered."))

        except Topic.DoesNotExist:
            # This should be caught by validate_topic_id, but good to be safe
            raise serializers.ValidationError(_("Invalid Topic ID referenced in answers."))
            
        for answer_data in value:
            question = answer_data['question']
            selected_choice_ids = answer_data.get('selected_choice_ids', [])
            
            if question.question_type in ['single-choice', 'multiple-choice']:
                if not selected_choice_ids:
                     raise serializers.ValidationError({f"question_{question.id}": _("No choice selected for a choice-based question.")})
                for choice in selected_choice_ids:
                    if choice.question != question:
                        raise serializers.ValidationError({f"choice_{choice.id}": _("Choice does not belong to the specified question.")})
            # Add validation for other question types if any
        return value

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        topic_id = validated_data['topic_id']
        answers_data = validated_data['answers']
        topic = Topic.objects.get(pk=topic_id)

        # Check if already attempted (if only one attempt is allowed, or for specific logic)
        # For now, we allow multiple attempts to be recorded, or this logic can be in the view.

        questions_in_topic = Question.objects.filter(topic=topic).prefetch_related('choices')
        total_questions_in_topic = questions_in_topic.count()
        correct_answers_count = 0

        quiz_attempt = QuizAttempt.objects.create(
            user=user,
            topic=topic,
            score=0, # Placeholder, will be updated
            correct_answers=0, # Placeholder
            total_questions_in_topic=total_questions_in_topic
        )

        for answer_data in answers_data:
            question = answer_data['question']
            selected_choices_data = answer_data.get('selected_choice_ids', [])
            
            # Determine if the submitted answer is correct
            is_answer_correct_for_question = False
            if question.question_type == 'single-choice':
                correct_choice = question.choices.filter(is_correct=True).first()
                if correct_choice and selected_choices_data and correct_choice == selected_choices_data[0]:
                    is_answer_correct_for_question = True
            elif question.question_type == 'multiple-choice':
                correct_choice_ids = set(question.choices.filter(is_correct=True).values_list('id', flat=True))
                selected_choice_ids_set = {choice.id for choice in selected_choices_data}
                if correct_choice_ids == selected_choice_ids_set:
                    is_answer_correct_for_question = True
            
            if is_answer_correct_for_question:
                correct_answers_count += 1

            user_answer = UserTopicAttemptAnswer.objects.create(
                quiz_attempt=quiz_attempt,
                question=question,
                is_correct=is_answer_correct_for_question
            )
            if selected_choices_data: # Add selected choices if any
                user_answer.selected_choices.set(selected_choices_data)
        
        # Update quiz_attempt score
        quiz_attempt.correct_answers = correct_answers_count
        quiz_attempt.score = (correct_answers_count / total_questions_in_topic) * 100 if total_questions_in_topic > 0 else 0
        
        # Link to TopicProgress and update it
        topic_progress, _ = TopicProgress.objects.get_or_create(
            user=user, 
            topic=topic,
            defaults={
                'course_progress': CourseProgress.objects.filter(user=user, course=topic.module.course).first()
            }
        )
        quiz_attempt.topic_progress = topic_progress
        quiz_attempt.save()

        # Mark topic as complete if quiz score meets a threshold (e.g., > 70%)
        # This logic can be customized. For now, any submission updates progress.
        # if quiz_attempt.score >= getattr(settings, 'QUIZ_PASS_THRESHOLD_PERCENT', 70):
        #     topic_progress.is_completed = True
        # topic_progress.save() # This will trigger CourseProgress update via signal

        return quiz_attempt # Return the attempt object

class QuizAttemptResultSerializer(serializers.ModelSerializer):
    """
    Serializer to show the results of a quiz attempt.
    """
    topic = TopicListSerializer(read_only=True)
    user_answers = UserTopicAttemptAnswerSerializer(many=True, read_only=True, source='answers')
    # We might want to include correct answers/explanations here for review
    questions_with_details = serializers.SerializerMethodField()

    class Meta:
        model = QuizAttempt
        fields = [
            'id', 'user_id', 'topic', 'score', 'correct_answers',
            'total_questions_in_topic', 'submitted_at', 'user_answers',
            'questions_with_details'
        ]

    def get_questions_with_details(self, obj):
        # For showing full questions, choices, and correct answers after attempt
        questions = Question.objects.filter(topic=obj.topic).prefetch_related('choices')
        return QuestionSerializer(questions, many=True, context=self.context).data
