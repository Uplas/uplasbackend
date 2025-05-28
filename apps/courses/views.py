from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.db.models import Prefetch, Q, Exists, OuterRef, Subquery

from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser

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
    QuestionSerializer, # ChoiceSerializer might not be directly used in a ViewSet
    EnrollmentSerializer, CourseReviewSerializer,
    TopicProgressSerializer, CourseProgressDetailSerializer,
    QuizSubmissionSerializer, QuizAttemptResultSerializer
)
from .permissions import (
    IsAdminOrReadOnly, IsInstructorOrReadOnly, IsEnrolled,
    CanViewTopicContent, CanPerformEnrolledAction, CanSubmitCourseReview
)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all() # Base queryset, refined in get_queryset
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category__slug', 'level', 'language', 'is_free', 'instructor__username']
    search_fields = ['title', 'short_description', 'long_description', 'instructor__full_name', 'category__name']
    ordering_fields = ['title', 'average_rating', 'total_enrollments', 'price', 'created_at', 'published_at']
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return CourseListSerializer
        if self.action in ['my_courses', 'instructor_courses']:
            return CourseListSerializer
        return CourseDetailSerializer

    def get_queryset(self):
        user = self.request.user
        base_qs = Course.objects.all()

        # Annotate with enrollment and progress for the current user if authenticated
        if user.is_authenticated:
            user_enrollments = Enrollment.objects.filter(user=user, course=OuterRef('pk'))
            user_progress = CourseProgress.objects.filter(user=user, course=OuterRef('pk'))
            
            base_qs = base_qs.annotate(
                _user_is_enrolled=Exists(user_enrollments),
                _user_progress_percentage=Subquery(user_progress.values('progress_percentage')[:1]),
                _user_last_accessed_topic_id=Subquery(user_progress.values('last_accessed_topic_id')[:1])
            )

        if self.action == 'list':
            qs = base_qs.select_related('category', 'instructor')
            if user.is_authenticated and user.is_staff:
                return qs.distinct() # Admins see all
            if user.is_authenticated:
                return qs.filter(Q(is_published=True) | Q(instructor=user)).distinct()
            return qs.filter(is_published=True).distinct()

        if self.action == 'retrieve':
            qs = base_qs.select_related('category', 'instructor').prefetch_related(
                Prefetch('modules', queryset=Module.objects.order_by('order').prefetch_related(
                    Prefetch('topics', queryset=Topic.objects.order_by('order').prefetch_related(
                        Prefetch('user_progresses', queryset=TopicProgress.objects.filter(user=user), to_attr='user_topic_progress_for_topic') # if user is authenticated
                    ) if user.is_authenticated else Topic.objects.order_by('order'))
                )),
                Prefetch('reviews', queryset=CourseReview.objects.select_related('user').order_by('-created_at'))
            )
            if user.is_authenticated and user.is_staff:
                return qs # Admins see all
            if user.is_authenticated and self.get_object().instructor == user: # Instructor sees their own unpublished
                return qs
            return qs.filter(is_published=True) # Others see only published

        # Default queryset
        if user.is_authenticated and user.is_staff:
            return base_qs.select_related('category', 'instructor').distinct()
        if user.is_authenticated:
            return base_qs.filter(Q(is_published=True) | Q(instructor=user)).select_related('category', 'instructor').distinct()
        return base_qs.filter(is_published=True).select_related('category', 'instructor').distinct()


    def get_permissions(self):
        if self.action == 'create':
            # Changed: Only Admin/Staff can create courses.
            # If instructors are not staff, a custom IsInstructor permission would be needed.
            self.permission_classes = [IsAdminUser]
        elif self.action in ['update', 'partial_update', 'destroy']:
            self.permission_classes = [IsInstructorOrReadOnly]
        elif self.action in ['enroll', 'get_my_progress']:
             # For 'enroll', the permission check is complex (free vs paid, already enrolled)
             # The view's action method handles this logic. IsAuthenticated is a baseline.
            self.permission_classes = [IsAuthenticated]
        elif self.action == 'submit_review':
            self.permission_classes = [IsAuthenticated, CanSubmitCourseReview]
        else: # list, retrieve, my_courses, instructor_courses
            self.permission_classes = [AllowAny] # Default for list/retrieve actions.
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(instructor=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def enroll(self, request, slug=None):
        course = self.get_object()
        user = request.user

        if Enrollment.objects.filter(user=user, course=course).exists():
            return Response({'detail': _('You are already enrolled in this course.')}, status=status.HTTP_400_BAD_REQUEST)

        if not course.is_free:
            return Response(
                {'detail': _('This is a paid course. Payment processing is required to enroll.')},
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

        enrollment_serializer = EnrollmentSerializer(data={'course_id': course.id}, context={'request': request})
        if enrollment_serializer.is_valid():
            enrollment_serializer.save(user=user)
            return Response({'detail': _('Successfully enrolled in the course.')}, status=status.HTTP_201_CREATED)
        return Response(enrollment_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_courses(self, request):
        enrollments = Enrollment.objects.filter(user=request.user).select_related(
            'course__category', 'course__instructor'
        )
        courses = [enrollment.course for enrollment in enrollments]
        # Annotate for serializer context
        for course in courses:
            course._user_is_enrolled = True # Since these are enrolled courses
            progress = CourseProgress.objects.filter(user=request.user, course=course).first()
            course._user_progress_percentage = progress.progress_percentage if progress else 0.0
            course._user_last_accessed_topic_id = progress.last_accessed_topic_id if progress else None

        serializer = self.get_serializer(courses, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def instructor_courses(self, request):
        # if not request.user.is_staff and not (hasattr(request.user, 'is_instructor') and request.user.is_instructor):
        #     return Response({"detail": _("User is not an instructor.")}, status=status.HTTP_403_FORBIDDEN)
        # Assuming IsAdminUser or a specific instructor role check for who can be an instructor.
        # For now, let's assume only staff or users marked as instructors on the user model can teach.
        # The feedback suggested IsAdminUser for course creation, so this should align.
        if not request.user.is_staff: # Simplified: only staff can be instructors for this view.
             return Response({"detail": _("Only instructors can view their courses.")}, status=status.HTTP_403_FORBIDDEN)

        courses = Course.objects.filter(instructor=request.user).select_related('category', 'instructor')
        serializer = self.get_serializer(courses, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, IsEnrolled])
    def get_my_progress(self, request, slug=None):
        course = self.get_object()
        progress = get_object_or_404(CourseProgress.objects.select_related('last_accessed_topic').prefetch_related('topic_progress_entries__topic'), user=request.user, course=course)
        serializer = CourseProgressDetailSerializer(progress, context={'request': request})
        return Response(serializer.data)


class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.all().order_by('order')
    permission_classes = [IsInstructorOrReadOnly]

    def get_serializer_class(self):
        if self.action == 'list':
            return ModuleListSerializer
        return ModuleDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related('course')
        course_slug = self.kwargs.get('course_slug')
        if course_slug:
            qs = qs.filter(course__slug=course_slug)
        
        if self.action == 'retrieve':
            user = self.request.user
            topic_qs = Topic.objects.order_by('order')
            if user.is_authenticated:
                topic_qs = topic_qs.prefetch_related(
                    Prefetch('user_progresses', queryset=TopicProgress.objects.filter(user=user), to_attr='user_topic_progress_for_topic')
                )
            qs = qs.prefetch_related(Prefetch('topics', queryset=topic_qs))
        return qs

    def perform_create(self, serializer):
        course_slug = self.kwargs.get('course_slug')
        course = get_object_or_404(Course, slug=course_slug)
        self.check_object_permissions(self.request, course)
        serializer.save(course=course)

    def perform_update(self, serializer):
        self.check_object_permissions(self.request, self.get_object().course)
        serializer.save(course=self.get_object().course)


class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all().order_by('order')
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return TopicListSerializer
        return TopicDetailSerializer

    def get_permissions(self):
        if self.action == 'retrieve':
            self.permission_classes = [CanViewTopicContent]
        else:
            self.permission_classes = [IsInstructorOrReadOnly]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset().select_related('module__course')
        module_id = self.kwargs.get('module_pk')
        if module_id:
            qs = qs.filter(module_id=module_id)

        if self.action == 'retrieve':
            user = self.request.user
            question_qs = Question.objects.order_by('order').prefetch_related('choices')
            qs = qs.prefetch_related(Prefetch('questions', queryset=question_qs))
            if user.is_authenticated:
                qs = qs.prefetch_related(
                     Prefetch('user_progresses', queryset=TopicProgress.objects.filter(user=user), to_attr='user_topic_progress_for_topic')
                )
        return qs

    def perform_create(self, serializer):
        module_id = self.kwargs.get('module_pk')
        module_obj = get_object_or_404(Module, pk=module_id)
        self.check_object_permissions(self.request, module_obj.course)
        serializer.save(module=module_obj)

    def perform_update(self, serializer):
        self.check_object_permissions(self.request, self.get_object().module.course)
        serializer.save()


    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanPerformEnrolledAction])
    def mark_as_complete(self, request, slug=None, module_pk=None, course_slug=None):
        topic = self.get_object()
        
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
            topic_progress.save()
        elif created:
            pass
        return Response({'detail': _('Topic marked as complete.')}, status=status.HTTP_200_OK)


class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [IsInstructorOrReadOnly]

    def get_queryset(self):
        topic_slug = self.kwargs.get('topic_slug')
        return Question.objects.filter(topic__slug=topic_slug).order_by('order').prefetch_related('choices')

    def perform_create(self, serializer):
        topic_slug = self.kwargs.get('topic_slug')
        topic_obj = get_object_or_404(Topic, slug=topic_slug)
        self.check_object_permissions(self.request, topic_obj.module.course)
        serializer.save(topic=topic_obj)

    def perform_update(self, serializer):
        self.check_object_permissions(self.request, self.get_object().topic.module.course)
        serializer.save()


class CourseReviewViewSet(viewsets.ModelViewSet):
    serializer_class = CourseReviewSerializer
    permission_classes = [IsAuthenticated] # Default, refined per action

    def get_queryset(self):
        course_slug = self.kwargs.get('course_slug')
        if course_slug:
            return CourseReview.objects.filter(course__slug=course_slug).select_related('user', 'course').order_by('-created_at')
        return CourseReview.objects.none()

    def get_permissions(self):
        if self.action == 'create':
            self.permission_classes = [IsAuthenticated, CanSubmitCourseReview]
        elif self.action in ['update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated, CanSubmitCourseReview] 
        return super().get_permissions()

    def perform_create(self, serializer):
        course_slug = self.kwargs.get('course_slug')
        course = get_object_or_404(Course, slug=course_slug)
        self.check_object_permissions(self.request, course) 
        serializer.save(user=self.request.user, course=course)


class QuizSubmissionView(generics.CreateAPIView):
    serializer_class = QuizSubmissionSerializer
    permission_classes = [IsAuthenticated] # Further checks in serializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Pass the topic object to the serializer if needed for complex validation beyond topic_id
        # topic_id = self.request.data.get('topic_id')
        # if topic_id:
        #     try:
        #         context['topic_instance'] = Topic.objects.get(pk=topic_id)
        #     except Topic.DoesNotExist:
        #         pass # Serializer will catch invalid topic_id
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Permission check for CanPerformEnrolledAction against the topic
        topic_id = serializer.validated_data.get('topic_id')
        topic = get_object_or_404(Topic, pk=topic_id)
        permission_checker = CanPerformEnrolledAction()
        if not permission_checker.has_object_permission(request, self, topic):
            self.permission_denied(request, message=getattr(permission_checker, 'message', None))

        quiz_attempt = serializer.save() # user is set from context by serializer.create
        result_serializer = QuizAttemptResultSerializer(quiz_attempt, context={'request': request})
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)


class QuizAttemptResultViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = QuizAttemptResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = QuizAttempt.objects.filter(user=user).select_related(
            'topic__module__course', 'user'
        ).prefetch_related(
            Prefetch('answers', queryset=UserTopicAttemptAnswer.objects.select_related('question').prefetch_related('selected_choices'))
        ).order_by('-submitted_at')
        
        topic_id = self.request.query_params.get('topic_id')
        if topic_id:
            qs = qs.filter(topic_id=topic_id)
        return qs
