from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.db.models import Prefetch

from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser

# Django Filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import (
    Category, Course, Module, Topic, Question, Choice,
    Enrollment, CourseReview, CourseProgress, TopicProgress,
    QuizAttempt, UserTopicAttemptAnswer
)
from .serializers import (
    CategorySerializer,
    CourseListSerializer, CourseDetailSerializer,
    ModuleListSerializer, ModuleDetailSerializer,
    TopicListSerializer, TopicDetailSerializer,
    QuestionSerializer, ChoiceSerializer, # ChoiceSerializer might not be directly used in a ViewSet
    EnrollmentSerializer, CourseReviewSerializer,
    TopicProgressSerializer, CourseProgressDetailSerializer,
    QuizSubmissionSerializer, QuizAttemptResultSerializer
)
from .permissions import (
    IsAdminOrReadOnly, IsInstructorOrReadOnly, IsEnrolled,
    CanViewTopicContent, CanPerformEnrolledAction, CanSubmitCourseReview
)

# --- ViewSets for Core Course Structure ---

class CategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing course categories.
    Admin users can create, update, delete. All users can list and retrieve.
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']


class CourseViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing courses.
    Instructors can create and manage their own courses.
    Students can list, retrieve, enroll, and review.
    """
    queryset = Course.objects.filter(is_published=True) # Default to published courses for general listing
    permission_classes = [AllowAny] # Default, overridden per action
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category__slug', 'level', 'language', 'is_free', 'instructor__username']
    search_fields = ['title', 'short_description', 'long_description', 'instructor__full_name', 'category__name']
    ordering_fields = ['title', 'average_rating', 'total_enrollments', 'price', 'created_at', 'published_at']
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return CourseListSerializer
        if self.action in ['my_courses', 'instructor_courses', 'enrolled_courses_summary']: # Assuming these custom actions exist
            return CourseListSerializer
        return CourseDetailSerializer

    def get_queryset(self):
        queryset = Course.objects.all()
        user = self.request.user

        # Instructors see their own unpublished courses, admins see all
        if user.is_authenticated:
            if user.is_staff: # Admins see all
                pass
            elif self.action in ['retrieve', 'list', 'my_courses', 'instructor_courses']: # Allow instructors to see their unpublished courses
                 # For list, we might want to union published courses and user's unpublished courses
                queryset = Course.objects.filter(models.Q(is_published=True) | models.Q(instructor=user))
            else: # Default for authenticated non-staff/non-instructor, only published
                queryset = queryset.filter(is_published=True)
        else: # Unauthenticated users only see published courses
            queryset = queryset.filter(is_published=True)

        # Optimize queries
        if self.action == 'list':
            queryset = queryset.select_related('category', 'instructor__userprofile')
        elif self.action == 'retrieve':
            queryset = queryset.select_related('category', 'instructor__userprofile').prefetch_related(
                Prefetch('modules', queryset=Module.objects.order_by('order').prefetch_related(
                    Prefetch('topics', queryset=Topic.objects.order_by('order'))
                )),
                Prefetch('reviews', queryset=CourseReview.objects.select_related('user__userprofile').order_by('-created_at')),
            )
        return queryset.distinct() # Ensure distinct results if Q objects cause duplicates

    def get_permissions(self):
        if self.action in ['create']:
            self.permission_classes = [IsAuthenticated] # Any authenticated user can propose a course (or restrict to instructors)
        elif self.action in ['update', 'partial_update', 'destroy']:
            self.permission_classes = [IsInstructorOrReadOnly]
        elif self.action in ['enroll', 'rate_course', 'get_my_progress']:
            self.permission_classes = [IsAuthenticated, IsEnrolled] # IsEnrolled checks object for rate_course
        elif self.action == 'submit_review': # Assuming a custom action, or handled by CourseReviewViewSet
            self.permission_classes = [IsAuthenticated, CanSubmitCourseReview]
        else: # list, retrieve, etc.
            self.permission_classes = [AllowAny]
        return super().get_permissions()

    def perform_create(self, serializer):
        # Assign the current user as the instructor
        serializer.save(instructor=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def enroll(self, request, slug=None):
        """
        Enrolls the current user in the specified course.
        Handles free courses directly, paid courses would need payment integration.
        """
        course = self.get_object()
        user = request.user

        if Enrollment.objects.filter(user=user, course=course).exists():
            return Response({'detail': _('You are already enrolled in this course.')}, status=status.HTTP_400_BAD_REQUEST)

        # TODO: Payment Integration for paid courses
        # If course.is_free is False:
        #   1. Check if payment is required (e.g., via a payment app or service)
        #   2. If payment is successful, then proceed to create enrollment.
        #   3. If payment fails or is pending, return appropriate response.
        #   For now, we'll assume payment is handled externally or course is free.
        if not course.is_free:
             # Placeholder: In a real app, this would redirect to a payment gateway or check payment status
            return Response(
                {'detail': _('This is a paid course. Payment processing is required to enroll.')},
                status=status.HTTP_402_PAYMENT_REQUIRED # Payment Required
            )

        enrollment_serializer = EnrollmentSerializer(data={'course_id': course.id}, context={'request': request})
        if enrollment_serializer.is_valid():
            enrollment_serializer.save(user=user) # Ensure user is set
            return Response({'detail': _('Successfully enrolled in the course.')}, status=status.HTTP_201_CREATED)
        return Response(enrollment_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_courses(self, request):
        """Lists courses the current authenticated user is enrolled in."""
        enrollments = Enrollment.objects.filter(user=request.user).select_related('course__category', 'course__instructor__userprofile')
        courses = [enrollment.course for enrollment in enrollments]
        serializer = self.get_serializer(courses, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated]) # Or IsInstructor permission
    def instructor_courses(self, request):
        """Lists courses taught by the current authenticated user."""
        if not hasattr(request.user, 'courses_taught'): # Check if user can be an instructor
             return Response({"detail": _("User is not an instructor.")}, status=status.HTTP_403_FORBIDDEN)
        courses = Course.objects.filter(instructor=request.user).select_related('category', 'instructor__userprofile')
        serializer = self.get_serializer(courses, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, IsEnrolled])
    def get_my_progress(self, request, slug=None):
        """Retrieves the current user's progress for this course."""
        course = self.get_object()
        progress = get_object_or_404(CourseProgress, user=request.user, course=course)
        serializer = CourseProgressDetailSerializer(progress, context={'request': request})
        return Response(serializer.data)

    # Reviews are handled by CourseReviewViewSet for better separation


class ModuleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing course modules.
    Nested under courses.
    """
    queryset = Module.objects.all().order_by('order')
    permission_classes = [IsInstructorOrReadOnly] # Object permission checks course instructor

    def get_serializer_class(self):
        if self.action == 'list':
            return ModuleListSerializer
        return ModuleDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        course_slug = self.kwargs.get('course_slug')
        if course_slug:
            qs = qs.filter(course__slug=course_slug)
        
        # Optimize
        if self.action == 'list':
            return qs.select_related('course')
        elif self.action == 'retrieve':
            return qs.select_related('course').prefetch_related(
                Prefetch('topics', queryset=Topic.objects.order_by('order'))
            )
        return qs

    def perform_create(self, serializer):
        course_slug = self.kwargs.get('course_slug')
        course = get_object_or_404(Course, slug=course_slug)
        # Check permission for the course
        self.check_object_permissions(self.request, course)
        serializer.save(course=course)

    def perform_update(self, serializer):
        # Ensure course is not changed on update
        serializer.save(course=self.get_object().course)


class TopicViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing course topics.
    Nested under modules.
    """
    queryset = Topic.objects.all().order_by('order')
    lookup_field = 'slug' # Or 'pk' if slugs are not unique across all topics

    def get_serializer_class(self):
        if self.action == 'list':
            return TopicListSerializer
        return TopicDetailSerializer

    def get_permissions(self):
        if self.action == 'retrieve':
            self.permission_classes = [CanViewTopicContent] # Checks enrollment, preview, free, instructor
        else: # create, update, partial_update, destroy, list
            self.permission_classes = [IsInstructorOrReadOnly] # Object permission checks course instructor
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        module_id = self.kwargs.get('module_pk') # Assuming module_pk from nested router
        if module_id:
            qs = qs.filter(module_id=module_id)

        # Optimize
        if self.action == 'retrieve':
            return qs.select_related('module__course').prefetch_related(
                Prefetch('questions', queryset=Question.objects.order_by('order').prefetch_related('choices'))
            )
        return qs.select_related('module__course')


    def perform_create(self, serializer):
        module_id = self.kwargs.get('module_pk')
        module_obj = get_object_or_404(Module, pk=module_id)
        # Check permission for the course associated with the module
        self.check_object_permissions(self.request, module_obj.course)
        serializer.save(module=module_obj)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanPerformEnrolledAction])
    def mark_as_complete(self, request, slug=None): # Or pk
        """Marks a topic as completed by the current user."""
        topic = self.get_object() # This will check CanPerformEnrolledAction's object permission
        
        # Get or create CourseProgress first
        course_progress, _ = CourseProgress.objects.get_or_create(
            user=request.user,
            course=topic.module.course,
            defaults={'enrollment': Enrollment.objects.filter(user=request.user, course=topic.module.course).first()}
        )

        topic_progress, created = TopicProgress.objects.get_or_create(
            user=request.user,
            topic=topic,
            defaults={'course_progress': course_progress, 'is_completed': True}
        )

        if not created and not topic_progress.is_completed:
            topic_progress.is_completed = True
            topic_progress.save() # This will trigger CourseProgress update via signal
        elif created: # Already set to completed via defaults
            pass # Signal in TopicProgress.save() handles CourseProgress update

        return Response({'detail': _('Topic marked as complete.')}, status=status.HTTP_200_OK)


class QuestionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing questions within a topic.
    Nested under topics.
    """
    serializer_class = QuestionSerializer
    permission_classes = [IsInstructorOrReadOnly] # Object permission checks course instructor

    def get_queryset(self):
        topic_slug = self.kwargs.get('topic_slug') # Assuming topic_slug from nested router
        return Question.objects.filter(topic__slug=topic_slug).order_by('order').prefetch_related('choices')

    def perform_create(self, serializer):
        topic_slug = self.kwargs.get('topic_slug')
        topic_obj = get_object_or_404(Topic, slug=topic_slug)
        # Check permission for the course associated with the topic
        self.check_object_permissions(self.request, topic_obj.module.course)
        serializer.save(topic=topic_obj)


# --- Views for Specific Actions (Enrollment, Reviews, Quizzes) ---

class CourseReviewViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing course reviews.
    Users can create reviews for courses they are enrolled in.
    Users can update/delete their own reviews.
    """
    serializer_class = CourseReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        course_slug = self.kwargs.get('course_slug')
        if course_slug:
            return CourseReview.objects.filter(course__slug=course_slug).select_related('user__userprofile', 'course').order_by('-created_at')
        return CourseReview.objects.none() # Require course context

    def get_permissions(self):
        if self.action == 'create':
            self.permission_classes = [IsAuthenticated, CanSubmitCourseReview]
        elif self.action in ['update', 'partial_update', 'destroy']:
            # CanSubmitCourseReview's has_object_permission handles ownership
            self.permission_classes = [IsAuthenticated, CanSubmitCourseReview] 
        return super().get_permissions()

    def perform_create(self, serializer):
        course_slug = self.kwargs.get('course_slug')
        course = get_object_or_404(Course, slug=course_slug)
        # CanSubmitCourseReview permission class will check if user can review this course
        self.check_object_permissions(self.request, course) # Pass course to permission
        serializer.save(user=self.request.user, course=course)


class QuizSubmissionView(generics.CreateAPIView):
    """
    API endpoint for submitting quiz answers for a topic.
    """
    serializer_class = QuizSubmissionSerializer
    permission_classes = [IsAuthenticated, CanPerformEnrolledAction] # CanPerformEnrolledAction checks enrollment via object

    def get_object(self): # Helper for permission check
        topic_id = self.request.data.get('topic_id')
        if not topic_id:
            raise generics.Http404("Topic ID not provided in request data.")
        topic = get_object_or_404(Topic, pk=topic_id)
        # This makes the topic object available to CanPerformEnrolledAction
        self.check_object_permissions(self.request, topic) 
        return topic
    
    def perform_create(self, serializer):
        # The permission check happens before this via get_object() if overridden like above,
        # or via the default mechanisms if has_object_permission is used by the permission class.
        # Ensure the topic object is correctly passed or handled by the permission.
        # For CreateAPIView, object permissions are not checked by default unless get_object is called.
        # We can explicitly call it or ensure the serializer does the necessary checks.
        # The QuizSubmissionSerializer already validates enrollment based on topic_id in its context.
        
        # Call get_object to ensure permission check on topic is done
        self.get_object() 
        
        quiz_attempt = serializer.save(user=self.request.user) # User passed implicitly via context to serializer
        # Return the result of the quiz attempt
        result_serializer = QuizAttemptResultSerializer(quiz_attempt, context={'request': self.request})
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)


class QuizAttemptResultViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for retrieving quiz attempt results.
    Users can see their own attempts. Instructors might see all attempts for their courses.
    """
    serializer_class = QuizAttemptResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Users can only see their own quiz attempts
        qs = QuizAttempt.objects.filter(user=user).select_related(
            'topic__module__course', 'user'
        ).prefetch_related(
            Prefetch('answers', queryset=UserTopicAttemptAnswer.objects.select_related('question').prefetch_related('selected_choices'))
        ).order_by('-submitted_at')
        
        topic_id = self.request.query_params.get('topic_id')
        if topic_id:
            qs = qs.filter(topic_id=topic_id)
            
        # TODO: Add instructor access to view attempts for their courses if needed
        # if user.is_staff or user_is_instructor_for_course:
        #    return QuizAttempt.objects.filter(topic__module__course__instructor=user)
        return qs
