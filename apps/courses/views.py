from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.db.models import Prefetch, Exists, OuterRef, Subquery, Count

from rest_framework import generics, viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError as DRFValidationError

from .models import (
    CourseCategory, Course, Module, Topic, Quiz, Question, AnswerOption,
    UserCourseEnrollment, UserTopicAttempt, Review
)
from .serializers import (
    CourseCategorySerializer, CourseSerializer, CourseDetailSerializer,
    ModuleSerializer, TopicSerializer, QuizSerializer, QuestionSerializer,
    UserCourseEnrollmentSerializer, UserTopicAttemptSerializer, ReviewSerializer,
    QuizSubmissionSerializer
)
from .permissions import IsInstructorOrReadOnly, IsEnrolledOrPreviewable, IsEnrolled

# Helper function for getting enrollment, could be a mixin
def get_user_enrollment(user, course_id_or_obj):
    if not user or not user.is_authenticated:
        return None
    try:
        course = course_id_or_obj if isinstance(course_id_or_obj, Course) else Course.objects.get(pk=course_id_or_obj)
        return UserCourseEnrollment.objects.select_related('course', 'user').get(user=user, course=course)
    except (Course.DoesNotExist, UserCourseEnrollment.DoesNotExist):
        return None

class CourseCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for listing and retrieving course categories.
    /api/courses/categories/
    """
    queryset = CourseCategory.objects.all()
    serializer_class = CourseCategorySerializer
    permission_classes = [permissions.AllowAny] # Categories are public

class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for listing and retrieving courses.
    Allows filtering by category, difficulty, and search terms.
    /api/courses/
    /api/courses/{course_slug}/
    """
    queryset = Course.objects.filter(is_published=True).prefetch_related(
        Prefetch('modules', queryset=Module.objects.order_by('order').prefetch_related(
            Prefetch('topics', queryset=Topic.objects.order_by('order'))
        )),
        'category',
        'instructor'
    )
    serializer_class = CourseSerializer
    permission_classes = [permissions.AllowAny] # Publicly viewable
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CourseDetailSerializer
        return CourseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # Annotate with enrollment status and progress if user is authenticated
        if user and user.is_authenticated:
            enrollment_subquery = UserCourseEnrollment.objects.filter(
                user=user,
                course=OuterRef('pk')
            )
            queryset = queryset.annotate(
                is_enrolled_annotated=Exists(enrollment_subquery),
                current_user_progress=Subquery(enrollment_subquery.values('progress_percentage')[:1])
            )
        
        # Filtering
        category_slug = self.request.query_params.get('category')
        difficulty = self.request.query_params.get('difficulty')
        search_term = self.request.query_params.get('search')
        instructor_id = self.request.query_params.get('instructor_id') # For instructor's courses

        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        if difficulty:
            queryset = queryset.filter(difficulty_level=difficulty)
        if search_term:
            queryset = queryset.filter(
                models.Q(title__icontains=search_term) |
                models.Q(description_html__icontains=search_term) |
                models.Q(subtitle__icontains=search_term)
            )
        if instructor_id:
            queryset = queryset.filter(instructor_id=instructor_id)
            
        return queryset

    @action(detail=True, methods=['get'], url_path='modules') # /api/courses/{course_slug}/modules/
    def list_modules(self, request, slug=None):
        course = self.get_object()
        modules = course.modules.order_by('order')
        serializer = ModuleSerializer(modules, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='enroll') # /api/courses/{course_slug}/enroll/ 
    def enroll(self, request, slug=None):
        course = self.get_object()
        user = request.user

        if UserCourseEnrollment.objects.filter(user=user, course=course).exists():
            return Response({'detail': _("You are already enrolled in this course.")}, status=status.HTTP_400_BAD_REQUEST)

        # TODO: Check for payment if course is not free
        if course.price > 0:
            # Here you would integrate with your payment system.
            # For now, let's assume payment is handled or it's a free course.
            # If payment is required and not made, return 402 Payment Required or similar.
            pass # Add payment check logic if applicable

        enrollment = UserCourseEnrollment.objects.create(user=user, course=course)
        course.total_enrollments = course.enrollments.count() # Update denormalized count
        course.save(update_fields=['total_enrollments'])
        
        serializer = UserCourseEnrollmentSerializer(enrollment, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[IsEnrolled], url_path='my-progress')
    def my_progress(self, request, slug=None):
        course = self.get_object()
        enrollment = get_user_enrollment(request.user, course)
        if not enrollment:
            raise NotFound(_("You are not enrolled in this course."))
        serializer = UserCourseEnrollmentSerializer(enrollment, context={'request': request})
        return Response(serializer.data)


class TopicViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for retrieving individual topics.
    Access might depend on enrollment or if topic is previewable.
    /api/courses/{course_slug}/modules/{module_id}/topics/{topic_slug}/ (Conceptual - we'll make a direct topic endpoint)
    /api/topics/{topic_slug}/ (direct access)
    """
    queryset = Topic.objects.select_related('module__course', 'quiz_details').all()
    serializer_class = TopicSerializer
    permission_classes = [IsEnrolledOrPreviewable] # Custom permission
    lookup_field = 'slug'

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Try to fetch enrollment if course context is available, to help TopicSerializer get user_progress
        # This is a bit complex; ideally, the enrollment is efficiently fetched
        topic_slug = self.kwargs.get(self.lookup_field) # or 'pk'
        if topic_slug:
            try:
                topic = Topic.objects.select_related('module__course').get(slug=topic_slug)
                enrollment = get_user_enrollment(self.request.user, topic.module.course)
                if enrollment:
                    context['enrollment'] = enrollment
            except Topic.DoesNotExist:
                pass # Will be handled by 404
        return context


    @action(detail=True, methods=['post'], permission_classes=[IsEnrolled], url_path='complete')
    def mark_as_complete(self, request, slug=None):
        topic = self.get_object()
        enrollment = get_user_enrollment(request.user, topic.module.course)
        if not enrollment:
            raise PermissionDenied(_("You must be enrolled in the course to mark topics complete."))

        if topic.content_type == 'quiz' and not UserTopicAttempt.objects.filter(enrollment=enrollment, topic=topic, passed=True).exists():
             return Response({'detail': _("You must pass the quiz associated with this topic to mark it complete.")}, status=status.HTTP_400_BAD_REQUEST)

        attempt, created = UserTopicAttempt.objects.get_or_create(
            enrollment=enrollment,
            topic=topic,
            user=request.user, # Added for consistency with model
            defaults={'is_completed': True, 'completed_at': timezone.now()}
        )

        if not attempt.is_completed:
            attempt.is_completed = True
            attempt.completed_at = timezone.now()
            attempt.save()
        
        # enrollment.update_progress() # Handled by signal in UserTopicAttempt.save()
        return Response({'status': _('Topic marked as complete.'), 'progress': enrollment.progress_percentage}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsEnrolled], url_path='uncomplete')
    def mark_as_uncomplete(self, request, slug=None):
        topic = self.get_object()
        enrollment = get_user_enrollment(request.user, topic.module.course)
        if not enrollment:
             raise PermissionDenied(_("You must be enrolled in the course."))

        attempt = get_object_or_404(UserTopicAttempt, enrollment=enrollment, topic=topic, user=request.user)
        if attempt.is_completed:
            attempt.is_completed = False
            # attempt.completed_at = None # Keep completion time if you want to track when it was last completed
            attempt.save()
        # enrollment.update_progress() # Handled by signal
        return Response({'status': _('Topic marked as not complete.'), 'progress': enrollment.progress_percentage}, status=status.HTTP_200_OK)


class ReviewViewSet(viewsets.ModelViewSet):
    """
    API endpoint for course reviews.
    List reviews for a course: /api/courses/{course_slug}/reviews/ 
    Create review for a course: (POST to the above)
    Manage own review: /api/reviews/{review_id}/
    """
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly] # Anyone can read, auth user to write/edit own

    def get_queryset(self):
        queryset = Review.objects.select_related('user', 'course').all()
        course_slug = self.kwargs.get('course_slug_from_url') # Injected from URL pattern

        if course_slug:
            course = get_object_or_404(Course, slug=course_slug)
            return queryset.filter(course=course)
        return queryset # For /api/reviews/{id} type access

    def perform_create(self, serializer):
        course_slug = self.kwargs.get('course_slug_from_url')
        course = get_object_or_404(Course, slug=course_slug)
        
        # Ensure user is enrolled to review (optional business rule, but common)
        enrollment = get_user_enrollment(self.request.user, course)
        if not enrollment:
            raise PermissionDenied(_("You must be enrolled in a course to review it."))
        # Prevent duplicate reviews handled by serializer's validate and model's unique_together

        serializer.save(user=self.request.user, course=course)
        course.total_enrollments = UserCourseEnrollment.objects.filter(course=course).count() # Re-calc for safety, or use F()
        course.save()

    def perform_update(self, serializer):
        review = self.get_object()
        if review.user != self.request.user:
            raise PermissionDenied(_("You can only edit your own reviews."))
        serializer.save()

    def perform_destroy(self, instance):
        if instance.user != self.request.user:
            raise PermissionDenied(_("You can only delete your own reviews."))
        course = instance.course
        instance.delete()
        # Rating update handled by signal


class MyCoursesViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for listing courses the current user is enrolled in.
    /api/my-courses/
    """
    serializer_class = UserCourseEnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return UserCourseEnrollment.objects.filter(user=user).select_related(
            'course__instructor', 'course__category', 'last_accessed_topic__module'
        ).order_by('-last_accessed_topic__last_accessed_at', '-enrolled_at') # Show most recently active first


class QuizSubmissionView(generics.GenericAPIView):
    """
    API endpoint for submitting quiz answers for a topic.
    POST /api/topics/{topic_slug}/submit-quiz/
    """
    serializer_class = QuizSubmissionSerializer
    permission_classes = [IsEnrolled] # Must be enrolled to submit quiz

    def post(self, request, topic_slug=None):
        topic = get_object_or_404(Topic.objects.select_related('quiz_details__questions__options'), slug=topic_slug, content_type='quiz')
        if not hasattr(topic, 'quiz_details'):
            raise NotFound(_("Quiz not found for this topic."))
        
        quiz = topic.quiz_details
        enrollment = get_user_enrollment(request.user, topic.module.course)
        if not enrollment: # Should be caught by IsEnrolled, but double check
            raise PermissionDenied(_("You are not enrolled in this course."))

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submitted_answers_data = serializer.validated_data['answers']

        total_score = 0
        max_possible_score = 0
        answer_history = []

        with transaction.atomic(): # Ensure all updates are one unit
            for answer_data in submitted_answers_data:
                question = get_object_or_404(Question.objects.prefetch_related('options'), pk=answer_data['question_id'], quiz=quiz)
                max_possible_score += question.points
                
                is_correct_submission = False
                user_answer_text = "" # For history

                if question.question_type in ['single_choice', 'multiple_choice', 'true_false']:
                    submitted_option_ids = set(str(opt_id) for opt_id in answer_data.get('answer_option_ids', []))
                    correct_option_ids = set(str(opt.id) for opt in question.options.filter(is_correct=True))
                    
                    user_answer_text = ", ".join(list(question.options.filter(id__in=submitted_option_ids).values_list('text', flat=True)))

                    if question.question_type == 'multiple_choice':
                        is_correct_submission = (submitted_option_ids == correct_option_ids)
                    else: # single_choice, true_false
                        is_correct_submission = bool(submitted_option_ids and (submitted_option_ids == correct_option_ids))
                
                elif question.question_type == 'short_answer':
                    # For short_answer, direct text comparison is tricky.
                    # Usually, correct answers for short_answer are stored as options with is_correct=True,
                    # and we check if the user's text_answer matches one of them (case-insensitive).
                    # Or use a more advanced NLP comparison if needed.
                    # Simple check: assume one correct AnswerOption text for short answer.
                    user_text_answer = answer_data.get('text_answer', '').strip()
                    user_answer_text = user_text_answer
                    correct_short_answers = [opt.text.strip().lower() for opt in question.options.filter(is_correct=True)]
                    if correct_short_answers and user_text_answer.lower() in correct_short_answers:
                        is_correct_submission = True
                    elif not correct_short_answers and not user_text_answer: # if correct is empty and user submitted empty
                        is_correct_submission = True 

                if is_correct_submission:
                    total_score += question.points
                
                answer_history.append({
                    'question_id': str(question.id),
                    'question_text': question.text,
                    'submitted_answer': user_answer_text,
                    'submitted_option_ids': [str(id) for id in answer_data.get('answer_option_ids', [])],
                    'is_correct': is_correct_submission,
                    'explanation': question.explanation if not is_correct_submission or question.explanation else None,
                    'points_awarded': question.points if is_correct_submission else 0
                })

            # Create or update UserTopicAttempt
            final_score_percentage = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
            passed_quiz = final_score_percentage >= quiz.pass_mark_percentage

            attempt, created = UserTopicAttempt.objects.update_or_create(
                enrollment=enrollment,
                topic=topic,
                user=request.user,
                defaults={
                    'score': final_score_percentage,
                    'passed': passed_quiz,
                    'is_completed': passed_quiz, # Mark topic complete if quiz passed
                    'completed_at': timezone.now() if passed_quiz else None,
                    'answer_history_json': answer_history,
                    'last_accessed_at': timezone.now()
                }
            )
            # enrollment.update_progress() # Handled by signal in UserTopicAttempt.save()

        return Response({
            'detail': _("Quiz submitted successfully."),
            'score_percentage': final_score_percentage,
            'passed': passed_quiz,
            'total_score': total_score,
            'max_possible_score': max_possible_score,
            'results': answer_history,
            'topic_attempt_id': attempt.id
        }, status=status.HTTP_200_OK)
