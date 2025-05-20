from django.shortcuts import get_object_or_404
from django.db import transaction, models
from django.utils import timezone
from django.db.models import Prefetch, Exists, OuterRef, Subquery, Count, Q, Avg

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
    ModuleSerializer, TopicSerializer, QuizSerializer, QuestionSerializer, # Ensure QuestionSerializer is imported
    UserCourseEnrollmentSerializer, UserTopicAttemptSerializer, ReviewSerializer,
    QuizSubmissionSerializer, SubmitAnswerSerializer # Ensure quiz submission serializers are imported
)
from .permissions import (
    IsInstructorOrReadOnly, IsEnrolledOrPreviewable, IsEnrolled, CanReviewCourse
)

# Helper to get enrollment, reducing redundancy
def get_user_enrollment_for_course(user, course_id_or_obj):
    if not user or not user.is_authenticated:
        return None
    try:
        course = course_id_or_obj if isinstance(course_id_or_obj, Course) else Course.objects.get(pk=course_id_or_obj)
        return UserCourseEnrollment.objects.select_related('course', 'user').get(user=user, course=course)
    except (Course.DoesNotExist, UserCourseEnrollment.DoesNotExist):
        return None

class CourseCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CourseCategory.objects.annotate(
        published_courses_count=Count('courses', filter=Q(courses__is_published=True))
    ).order_by('display_order', 'name')
    serializer_class = CourseCategorySerializer
    permission_classes = [permissions.AllowAny]

class CourseViewSet(viewsets.ModelViewSet): # Changed to ModelViewSet for potential admin creation
    serializer_class = CourseSerializer
    permission_classes = [IsInstructorOrReadOnly] # ReadOnly for non-instructors, full for instructor
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        # Base queryset: all courses for instructors/staff, only published for others
        if user.is_authenticated and (user.is_staff or user.is_superuser): # Or a specific 'instructor' role
            queryset = Course.objects.all()
        else:
            queryset = Course.objects.filter(is_published=True, published_date__lte=timezone.now())

        queryset = queryset.select_related('category', 'instructor__profile').annotate( # instructor.profile if you store avatar there
            # average_rating_annotated=Avg('reviews__rating'), # Already on model, but could be done here
            # total_enrollments_annotated=Count('enrollments', distinct=True) # Already on model
        )
        
        # Annotate with enrollment status and progress if user is authenticated for list view
        if user.is_authenticated:
            enrollment_subquery = UserCourseEnrollment.objects.filter(user=user, course=OuterRef('pk'))
            queryset = queryset.annotate(
                is_enrolled_annotated=Exists(enrollment_subquery),
                current_user_progress_annotated=Subquery(enrollment_subquery.values('progress_percentage')[:1])
            )
        
        # Filtering for list view
        if self.action == 'list':
            category_slug = self.request.query_params.get('category')
            difficulty = self.request.query_params.get('difficulty')
            search_term = self.request.query_params.get('search')
            instructor_id = self.request.query_params.get('instructor_id')

            if category_slug:
                queryset = queryset.filter(category__slug=category_slug)
            if difficulty:
                queryset = queryset.filter(difficulty_level=difficulty)
            if search_term:
                queryset = queryset.filter(
                    Q(title__icontains=search_term) |
                    Q(description_html__icontains=search_term) |
                    Q(subtitle__icontains=search_term) |
                    Q(tags__name__icontains=search_term) # Assuming you add M2M tags to Course later
                ).distinct()
            if instructor_id:
                queryset = queryset.filter(instructor_id=instructor_id)
            
        return queryset.order_by('-is_published', '-published_date', 'title') # Show published first


    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CourseDetailSerializer
        return CourseSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        # For 'retrieve' action, pre-fetch enrollment for the specific course
        if self.action == 'retrieve' and user.is_authenticated:
            try:
                course_slug = self.kwargs.get(self.lookup_field)
                course = Course.objects.get(slug=course_slug) # Should be self.get_object() but that calls get_queryset first
                enrollment = UserCourseEnrollment.objects.filter(user=user, course=course).first()
                if enrollment:
                    context[f'enrollment_course_{course.id}'] = enrollment
            except Course.DoesNotExist:
                pass # Handled by 404
        return context

    def perform_create(self, serializer): # Only instructors/admin should create
        if not self.request.user.is_staff: # Or check for specific instructor role
            raise PermissionDenied("You do not have permission to create courses.")
        serializer.save(instructor=self.request.user)

    @action(detail=True, methods=['get'], url_path='modules', serializer_class=ModuleSerializer)
    def list_modules(self, request, slug=None):
        course = self.get_object() # Applies IsInstructorOrReadOnly for course access
        # Further permission: If modules should only be listed for enrolled users (unless previewable parts)
        # For now, assuming if user can see course, they can see module list.
        # Content access is per-topic via IsEnrolledOrPreviewable.
        
        # Prefetch topics for each module to optimize
        modules_with_topics = course.modules.prefetch_related(
            Prefetch('topics', queryset=Topic.objects.order_by('order'))
        ).order_by('order')
        
        serializer = self.get_serializer(modules_with_topics, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='enroll')
    def enroll(self, request, slug=None):
        course = self.get_object() # Course is public or user is instructor
        user = request.user

        if UserCourseEnrollment.objects.filter(user=user, course=course).exists():
            return Response({'detail': _("You are already enrolled in this course.")}, status=status.HTTP_400_BAD_REQUEST)

        if course.price > 0: # Basic check, real payment flow is more complex
            # TODO: Integrate with payment system. For now, assume paid or free.
            # This might redirect to a payment page or check user's subscription.
            # If payments app sets user.is_premium_subscriber, check that.
            if not user.is_premium_subscriber: # Simplified check
                 pass # return Response({'detail': _("Payment or active subscription required for this course.")}, status=status.HTTP_402_PAYMENT_REQUIRED)

        with transaction.atomic():
            enrollment = UserCourseEnrollment.objects.create(user=user, course=course)
            # Denormalized total_enrollments is updated by signal on UserCourseEnrollment save.
        
        serializer = UserCourseEnrollmentSerializer(enrollment, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[IsEnrolled], url_path='my-progress', serializer_class=UserCourseEnrollmentSerializer)
    def my_progress(self, request, slug=None):
        course = self.get_object() # Checks course existence and publish status
        # IsEnrolled permission checks if user is enrolled in *this specific course*
        enrollment = get_user_enrollment_for_course(request.user, course)
        # Enrollment should exist due to IsEnrolled permission, but double check
        if not enrollment:
             # This case should ideally not be reached if IsEnrolled works correctly for the object
            raise NotFound(_("Enrollment record not found for this course."))
        serializer = self.get_serializer(enrollment, context={'request': request})
        return Response(serializer.data)

class TopicViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Topic.objects.select_related(
        'module__course', 'quiz_details' # quiz_details for QuizSerializer if topic is a quiz
    ).prefetch_related(
        Prefetch('quiz_details__questions__options') # For quiz questions and their options
    ).order_by('module__order', 'order')
    serializer_class = TopicSerializer
    permission_classes = [IsEnrolledOrPreviewable]
    lookup_field = 'slug'

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        topic_slug = self.kwargs.get(self.lookup_field)
        
        if topic_slug and user and user.is_authenticated:
            try:
                # Fetch topic to get its course context for enrollment check efficiency
                topic = Topic.objects.select_related('module__course').get(slug=topic_slug)
                enrollment = UserCourseEnrollment.objects.filter(user=user, course=topic.module.course).first()
                if enrollment:
                    context[f'enrollment_course_{topic.module.course_id}'] = enrollment
                # If the action is 'retrieve' and topic is a quiz, set 'student_view' for QuestionSerializer
                if self.action == 'retrieve' and topic.content_type == 'quiz':
                    context['student_view'] = True # So students don't see is_correct for options
            except Topic.DoesNotExist:
                pass # Handled by 404
        return context
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object() # Permission IsEnrolledOrPreviewable applied
        # Optionally, log topic view event here if needed
        serializer = self.get_serializer(instance, context=self.get_serializer_context()) # Pass context
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsEnrolled], url_path='complete')
    def mark_as_complete(self, request, slug=None):
        topic = self.get_object() # IsEnrolled permission implies user is enrolled in topic's course
        enrollment = get_user_enrollment_for_course(request.user, topic.module.course)
        # Enrollment should exist due to IsEnrolled permission.

        if topic.content_type == 'quiz':
            attempt = UserTopicAttempt.objects.filter(enrollment=enrollment, topic=topic).first()
            if not attempt or not attempt.passed:
                 return Response({'detail': _("You must pass the quiz to mark this topic complete.")}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            attempt, created = UserTopicAttempt.objects.update_or_create(
                enrollment=enrollment, topic=topic, user=request.user,
                defaults={'is_completed': True, 'completed_at': timezone.now()}
            )
            if not created and not attempt.is_completed: # If existed but wasn't complete
                attempt.is_completed = True
                attempt.completed_at = timezone.now()
                attempt.save() # This will trigger enrollment.update_progress via signal
        
        # enrollment.update_progress() is handled by UserTopicAttempt signal
        enrollment.refresh_from_db() # Get updated progress
        return Response({'status': _('Topic marked as complete.'), 'progress': enrollment.progress_percentage}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsEnrolled], url_path='uncomplete')
    def mark_as_uncomplete(self, request, slug=None):
        topic = self.get_object()
        enrollment = get_user_enrollment_for_course(request.user, topic.module.course)

        with transaction.atomic():
            attempt = get_object_or_404(UserTopicAttempt, enrollment=enrollment, topic=topic, user=request.user)
            if attempt.is_completed:
                attempt.is_completed = False
                # attempt.completed_at = None # Keep if you want to track when it was last completed
                attempt.passed = False if topic.content_type == 'quiz' else None # Reset passed status for quiz
                attempt.save() # Triggers progress update
        
        enrollment.refresh_from_db()
        return Response({'status': _('Topic marked as not complete.'), 'progress': enrollment.progress_percentage}, status=status.HTTP_200_OK)


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, CanReviewCourse] # CanReviewCourse for object permissions

    def get_queryset(self):
        queryset = Review.objects.select_related('user__profile', 'course').all() # user.profile for avatar
        course_slug = self.kwargs.get('course_slug_from_url') # Injected from URL pattern using course_slug_from_url

        if course_slug:
            return queryset.filter(course__slug=course_slug)
        # If accessing /api/reviews/{review_id}/ directly (not nested)
        return queryset

    def perform_create(self, serializer):
        course_slug = self.kwargs.get('course_slug_from_url')
        course = get_object_or_404(Course, slug=course_slug)
        
        # Check enrollment - business rule, not strictly auth
        enrollment = get_user_enrollment_for_course(self.request.user, course)
        if not enrollment:
            raise PermissionDenied(_("You must be enrolled in a course to review it."))
        
        if Review.objects.filter(course=course, user=self.request.user).exists():
            raise DRFValidationError(_("You have already reviewed this course."))

        serializer.save(user=self.request.user, course=course)
        # Course average_rating and total_reviews updated by signals from Review model

    # perform_update and perform_destroy use CanReviewCourse.has_object_permission

class MyCoursesViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserCourseEnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return UserCourseEnrollment.objects.filter(user=user).select_related(
            'course__instructor__profile', 'course__category', 'last_accessed_topic__module'
        ).prefetch_related( # Prefetch M2M on course if needed in serializer
            # Prefetch('course__tags') 
        ).order_by('-last_accessed_topic__last_accessed_at', '-enrolled_at')

class QuizSubmissionView(generics.GenericAPIView): # Changed from APIView to GenericAPIView for get_serializer
    serializer_class = QuizSubmissionSerializer
    permission_classes = [IsEnrolled]

    def get_serializer_context(self): # Pass request to serializer if needed
        return {'request': self.request}

    def post(self, request, topic_slug=None): # topic_slug from URL
        topic = get_object_or_404(
            Topic.objects.select_related('quiz_details', 'module__course'), 
            slug=topic_slug, content_type='quiz'
        )
        # IsEnrolled permission checks if user is enrolled in topic.module.course

        if not hasattr(topic, 'quiz_details') or not topic.quiz_details:
            raise NotFound(_("Quiz not found for this topic."))
        
        quiz = topic.quiz_details
        enrollment = get_user_enrollment_for_course(request.user, topic.module.course)
        # Enrollment should exist due to IsEnrolled permission.

        serializer = self.get_serializer(data=request.data) # Uses self.serializer_class
        serializer.is_valid(raise_exception=True)
        submitted_answers_data = serializer.validated_data['answers']

        total_score_achieved = 0
        max_possible_score = 0
        answer_history_log = [] # For UserTopicAttempt.answer_history_json

        with transaction.atomic():
            # Pre-fetch all questions and their correct options for this quiz for efficiency
            quiz_questions = Question.objects.filter(quiz=quiz).prefetch_related('options')
            questions_map = {str(q.id): q for q in quiz_questions}
            
            for answer_data in submitted_answers_data:
                question_id_str = str(answer_data['question_id'])
                question = questions_map.get(question_id_str)

                if not question: # Should not happen if validation is good, but safeguard
                    # Log this anomaly, maybe raise error or skip
                    print(f"Warning: Submitted answer for unknown question ID {question_id_str} in quiz {quiz.id}")
                    continue
                
                max_possible_score += question.points
                is_correct_submission = False
                submitted_option_texts = [] # For logging

                if question.question_type in ['single_choice', 'multiple_choice', 'true_false']:
                    submitted_option_ids = set(str(opt_id) for opt_id in answer_data.get('answer_option_ids', []))
                    correct_option_ids = set(str(opt.id) for opt in question.options.filter(is_correct=True))
                    
                    # Get texts for submitted options for logging
                    for opt in question.options.all():
                        if str(opt.id) in submitted_option_ids:
                            submitted_option_texts.append(opt.text)

                    if question.question_type == 'multiple_choice':
                        is_correct_submission = (submitted_option_ids == correct_option_ids)
                    else: # single_choice, true_false (exactly one correct option expected)
                        is_correct_submission = bool(submitted_option_ids and (submitted_option_ids == correct_option_ids) and len(correct_option_ids) == 1)
                
                elif question.question_type == 'short_answer':
                    user_text_answer = answer_data.get('text_answer', '').strip().lower()
                    submitted_option_texts.append(user_text_answer) # Log the text answer
                    correct_short_answers = [opt.text.strip().lower() for opt in question.options.filter(is_correct=True)]
                    if correct_short_answers and user_text_answer in correct_short_answers:
                        is_correct_submission = True
                    # Consider partial credit or more advanced matching for short answers if needed

                if is_correct_submission:
                    total_score_achieved += question.points
                
                answer_history_log.append({
                    'question_id': str(question.id),
                    'question_text': question.text,
                    'submitted_answer_options_ids': list(submitted_option_ids) if question.question_type not in ['short_answer'] else [],
                    'submitted_text_answer': user_text_answer if question.question_type == 'short_answer' else None,
                    'submitted_options_text': submitted_option_texts, # Log what user selected/entered
                    'is_correct': is_correct_submission,
                    'explanation': question.explanation, # Always provide explanation for review
                    'points_awarded': question.points if is_correct_submission else 0
                })

            final_score_percentage = (total_score_achieved / max_possible_score) * 100 if max_possible_score > 0 else 0.0
            passed_quiz = final_score_percentage >= quiz.pass_mark_percentage

            attempt, created = UserTopicAttempt.objects.update_or_create(
                enrollment=enrollment, topic=topic, user=request.user,
                defaults={
                    'score': final_score_percentage,
                    'passed': passed_quiz,
                    'is_completed': passed_quiz, # Mark topic complete if quiz passed
                    'completed_at': timezone.now() if passed_quiz else None,
                    'answer_history_json': answer_history_log,
                    'last_accessed_at': timezone.now() # Update last accessed
                }
            )
            # UserTopicAttempt.save() signal will handle enrollment.update_progress()

        return Response({
            'detail': _("Quiz submitted successfully."),
            'score_percentage': round(final_score_percentage, 2),
            'passed': passed_quiz,
            'total_score_achieved': total_score_achieved,
            'max_possible_score': max_possible_score,
            'results': answer_history_log, # Detailed results for immediate feedback
            'topic_attempt_id': attempt.id
        }, status=status.HTTP_200_OK)
