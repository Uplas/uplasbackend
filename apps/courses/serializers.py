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

class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'email']

class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ['id', 'text', 'is_correct', 'order']
        read_only_fields = ['id']

class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(many=True, read_only=False)

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
        
        instance.text = validated_data.get('text', instance.text)
        instance.question_type = validated_data.get('question_type', instance.question_type)
        instance.order = validated_data.get('order', instance.order)
        instance.explanation = validated_data.get('explanation', instance.explanation)
        instance.save()

        if choices_data is not None:
            # Current strategy: Delete existing choices and create new ones.
            # Feedback: "For frequent updates or complex choices, this might be inefficient...
            # Consider a more granular update strategy for choices if needed."
            # For now, keeping the simpler approach. A granular approach would involve
            # matching by ID, updating existing, deleting removed, and adding new ones.
            instance.choices.all().delete()
            for choice_data in choices_data:
                Choice.objects.create(question=instance, **choice_data)
        
        return instance


class TopicListSerializer(serializers.ModelSerializer):
    module_title = serializers.CharField(source='module.title', read_only=True)
    course_id = serializers.UUIDField(source='module.course.id', read_only=True)

    class Meta:
        model = Topic
        fields = [
            'id', 'title', 'slug', 'order', 'estimated_duration_minutes',
            'is_previewable', 'module_id', 'module_title', 'course_id'
        ]

class TopicDetailSerializer(serializers.ModelSerializer):
    module_title = serializers.CharField(source='module.title', read_only=True)
    course_id = serializers.UUIDField(source='module.course.id', read_only=True)
    questions = QuestionSerializer(many=True, read_only=True)
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

    def validate_content(self, value):
        """
        Validates the schema for the Topic.content JSONField.
        Example schema:
        {
          "type": "text" | "video" | "quiz" | "external_resource",
          "text_content": "Markdown or HTML for text type",
          "video_url": "URL for video type",
          "resource_url": "URL for external resource type"
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
            raise serializers.ValidationError(_(f"Invalid content type '{content_type}'. Allowed types are: {', '.join(allowed_types)}."))

        if content_type == "text" and not value.get("text_content"):
            raise serializers.ValidationError(_("Text content must have a 'text_content' field."))
        if content_type == "video" and not value.get("video_url"):
            raise serializers.ValidationError(_("Video content must have a 'video_url' field."))
        if content_type == "external_resource" and not value.get("resource_url"):
            raise serializers.ValidationError(_("External resource content must have a 'resource_url' field."))
        if content_type == "code_interactive":
            if not value.get("code_language") or not value.get("initial_code"):
                raise serializers.ValidationError(_("Code interactive content must have 'code_language' and 'initial_code' fields."))
        # For 'quiz' type, the presence of questions linked to the topic is the primary validation,
        # handled by how questions are managed.
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
            # This could be optimized if TopicProgress is prefetched with the Topic
            return TopicProgress.objects.filter(user=user, topic=obj, is_completed=True).exists()
        return False

class TopicProgressSerializer(serializers.ModelSerializer):
    topic_title = serializers.CharField(source='topic.title', read_only=True)
    class Meta:
        model = TopicProgress
        fields = ['id', 'user_id', 'topic_id', 'topic_title', 'is_completed', 'completed_at']
        read_only_fields = ['id', 'user_id', 'topic_title', 'completed_at']

class ModuleListSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    class Meta:
        model = Module
        fields = ['id', 'title', 'order', 'description', 'course_id', 'course_title']

class ModuleDetailSerializer(serializers.ModelSerializer):
    topics = TopicListSerializer(many=True, read_only=True)
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
        user = self.context['request'].user
        if user and user.is_authenticated:
            # Optimized: Fetch all topic progresses for the module's topics for this user in one go if possible
            # This is often better done in the ViewSet's get_queryset with prefetch_related for the module's topics
            # and then their related TopicProgress for the current user.
            # For simplicity here, we query.
            module_topics = obj.topics.all()
            total_topics_count = module_topics.count()
            if total_topics_count == 0:
                return 0.0
            completed_topics_count = TopicProgress.objects.filter(
                user=user,
                topic__in=module_topics, # Filter by topics belonging to this module
                is_completed=True
            ).count()
            return (completed_topics_count / total_topics_count) * 100
        return 0.0


class CourseReviewSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True, required=False # User set from request
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
        user = request.user # User set from request in view
        course = data.get('course') # This is the Course instance

        if self.instance: 
            if self.instance.user != user and not user.is_staff:
                raise serializers.ValidationError(_("You can only edit your own reviews."))
        else: 
            if not Enrollment.objects.filter(user=user, course=course).exists():
                 raise serializers.ValidationError(_("You must be enrolled in this course to submit a review."))
            if CourseReview.objects.filter(user=user, course=course).exists():
                raise serializers.ValidationError(_("You have already reviewed this course."))
        return data

class CourseListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    instructor_name = serializers.CharField(source='instructor.get_full_name', read_only=True, allow_null=True)
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
        user = self.context['request'].user
        if user and user.is_authenticated:
            # Optimized approach: If enrollments are prefetched for the user, check against that.
            # If not, this causes N+1 queries in a list.
            # The CourseViewSet's get_queryset should ideally prefetch this for 'list' action.
            return Enrollment.objects.filter(user=user, course=obj).exists()
        return False

class CourseDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    instructor = SimpleUserSerializer(read_only=True)
    modules = ModuleDetailSerializer(many=True, read_only=True)
    reviews = CourseReviewSerializer(many=True, read_only=True, source='reviews')
    
    is_enrolled = serializers.SerializerMethodField()
    user_progress_percentage = serializers.SerializerMethodField()
    last_accessed_topic_id = serializers.SerializerMethodField()

    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False, allow_null=True
    )

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
        user = self.context['request'].user
        if user and user.is_authenticated:
            # Optimized: ViewSet get_queryset for retrieve should pass enrollment status in context or annotation
            # Fallback to query if not optimized in view:
            if hasattr(obj, '_user_is_enrolled'): # Check if annotated by the view
                return obj._user_is_enrolled
            return Enrollment.objects.filter(user=user, course=obj).exists()
        return False

    def get_user_progress_percentage(self, obj):
        user = self.context['request'].user
        if user and user.is_authenticated:
            # Optimized: ViewSet get_queryset for retrieve should pass progress in context or annotation
            if hasattr(obj, '_user_progress_percentage'):
                return obj._user_progress_percentage
            progress = CourseProgress.objects.filter(user=user, course=obj).first()
            return progress.progress_percentage if progress else 0.0
        return 0.0
    
    def get_last_accessed_topic_id(self, obj):
        user = self.context['request'].user
        if user and user.is_authenticated:
            if hasattr(obj, '_user_last_accessed_topic_id'):
                return obj._user_last_accessed_topic_id
            progress = CourseProgress.objects.filter(user=user, course=obj).first()
            return progress.last_accessed_topic_id if progress and progress.last_accessed_topic_id else None
        return None

    def create(self, validated_data):
        validated_data['instructor'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'instructor' in validated_data and not self.context['request'].user.is_staff:
            validated_data.pop('instructor')
        return super().update(instance, validated_data)


class EnrollmentSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True, required=False
    )
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.filter(is_published=True), source='course', write_only=True # Ensure enrolling in published course
    )
    user_email = serializers.EmailField(source='user.email', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Enrollment
        fields = ['id', 'user_id', 'course_id', 'user_email', 'course_title', 'enrolled_at']
        read_only_fields = ['id', 'user_email', 'course_title', 'enrolled_at']

    def validate(self, data):
        user = self.context['request'].user
        course = data.get('course')

        if Enrollment.objects.filter(user=user, course=course).exists():
            raise serializers.ValidationError(_("You are already enrolled in this course."))
        
        # Payment check is handled in the view's 'enroll' action
        return data
    
    def create(self, validated_data):
        if 'user' not in validated_data: # User should be from context
            validated_data['user'] = self.context['request'].user
        
        enrollment = super().create(validated_data)
        CourseProgress.objects.get_or_create(
            user=enrollment.user,
            course=enrollment.course,
            defaults={'enrollment': enrollment}
        )
        return enrollment

class CourseProgressDetailSerializer(serializers.ModelSerializer):
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

class UserTopicAttemptAnswerSerializer(serializers.ModelSerializer):
    question_id = serializers.PrimaryKeyRelatedField(queryset=Question.objects.all(), source='question')
    selected_choice_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=Choice.objects.all()),
        write_only=True,
        required=False
    )

    class Meta:
        model = UserTopicAttemptAnswer
        fields = ['question_id', 'selected_choice_ids']

class QuizSubmissionSerializer(serializers.Serializer):
    topic_id = serializers.UUIDField()
    answers = UserTopicAttemptAnswerSerializer(many=True)

    def validate_topic_id(self, value):
        try:
            topic = Topic.objects.get(pk=value)
        except Topic.DoesNotExist:
            raise serializers.ValidationError(_("Invalid Topic ID."))
        
        user = self.context['request'].user
        # Allow instructors/staff to submit even if not enrolled for testing
        if not (user.is_staff or topic.module.course.instructor == user):
            if not Enrollment.objects.filter(user=user, course=topic.module.course).exists():
                 raise serializers.ValidationError(_("You must be enrolled in the course to submit this quiz."))
        return value

    def validate_answers(self, value):
        if not value:
            raise serializers.ValidationError(_("Answers list cannot be empty."))
        
        topic_id = self.initial_data.get('topic_id')
        question_ids_in_submission = {str(ans['question'].id) for ans in value} # Ensure consistent type for comparison
        
        try:
            topic = Topic.objects.get(pk=topic_id)
            questions_in_topic = Question.objects.filter(topic=topic)
            question_ids_in_topic = {str(q.id) for q in questions_in_topic}

            if not question_ids_in_submission.issubset(question_ids_in_topic):
                raise serializers.ValidationError(_("One or more submitted question IDs do not belong to this topic."))

        except Topic.DoesNotExist:
            raise serializers.ValidationError(_("Invalid Topic ID referenced in answers."))
            
        for answer_data in value:
            question = answer_data['question']
            selected_choices_data = answer_data.get('selected_choice_ids', [])
            
            if question.question_type in ['single-choice', 'multiple-choice']:
                if not selected_choices_data:
                     raise serializers.ValidationError({f"question_{question.id}": _("No choice selected for a choice-based question.")})
                for choice in selected_choices_data:
                    if choice.question != question:
                        raise serializers.ValidationError({f"choice_{choice.id}": _("Choice does not belong to the specified question.")})
        return value

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        topic_id = validated_data['topic_id']
        answers_data = validated_data['answers']
        topic = Topic.objects.get(pk=topic_id)

        questions_in_topic = Question.objects.filter(topic=topic).prefetch_related('choices')
        total_questions_in_topic_count = questions_in_topic.count()
        correct_answers_count = 0

        quiz_attempt = QuizAttempt.objects.create(
            user=user,
            topic=topic,
            score=0, 
            correct_answers=0, 
            total_questions_in_topic=total_questions_in_topic_count
        )

        for answer_data in answers_data:
            question = answer_data['question']
            selected_choices_data = answer_data.get('selected_choice_ids', [])
            
            is_answer_correct_for_question = False
            if question.question_type == 'single-choice':
                correct_choice = question.choices.filter(is_correct=True).first()
                if correct_choice and selected_choices_data and correct_choice == selected_choices_data[0]:
                    is_answer_correct_for_question = True
            elif question.question_type == 'multiple-choice':
                correct_choice_ids = set(question.choices.filter(is_correct=True).values_list('id', flat=True))
                selected_choice_ids_set = {choice.id for choice in selected_choices_data}
                if correct_choice_ids == selected_choice_ids_set and len(correct_choice_ids) == len(selected_choice_ids_set): # Ensure all correct and no incorrect are selected
                    is_answer_correct_for_question = True
            
            if is_answer_correct_for_question:
                correct_answers_count += 1

            user_answer = UserTopicAttemptAnswer.objects.create(
                quiz_attempt=quiz_attempt,
                question=question,
                is_correct=is_answer_correct_for_question
            )
            if selected_choices_data:
                user_answer.selected_choices.set(selected_choices_data)
        
        quiz_attempt.correct_answers = correct_answers_count
        quiz_attempt.score = (correct_answers_count / total_questions_in_topic_count) * 100 if total_questions_in_topic_count > 0 else 0
        
        topic_progress, _ = TopicProgress.objects.get_or_create(
            user=user, 
            topic=topic,
            defaults={
                'course_progress': CourseProgress.objects.filter(user=user, course=topic.module.course).first()
            }
        )
        quiz_attempt.topic_progress = topic_progress
        quiz_attempt.save()
        
        return quiz_attempt

class QuizAttemptResultSerializer(serializers.ModelSerializer):
    topic = TopicListSerializer(read_only=True)
    user_answers_data = UserTopicAttemptAnswerSerializer(many=True, read_only=True, source='answers') # Renamed from user_answers
    questions_with_details = serializers.SerializerMethodField()

    class Meta:
        model = QuizAttempt
        fields = [
            'id', 'user_id', 'topic', 'score', 'correct_answers',
            'total_questions_in_topic', 'submitted_at', 'user_answers_data', # Renamed
            'questions_with_details'
        ]

    def get_questions_with_details(self, obj):
        questions = Question.objects.filter(topic=obj.topic).prefetch_related('choices')
        return QuestionSerializer(questions, many=True, context=self.context).data
