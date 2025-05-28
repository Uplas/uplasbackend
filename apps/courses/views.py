from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.db.models import Prefetch, Q, Exists, OuterRef, Subquery, Count
from django.utils import timezone # For CourseProgress creation
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
    QuestionSerializer,
    EnrollmentSerializer, CourseReviewSerializer,
    TopicProgressSerializer, CourseProgressDetailSerializer,
    QuizSubmissionSerializer, QuizAttemptResultSerializer
)
from .permissions import (
    IsAdminOrReadOnly, IsInstructorOrReadOnly, IsEnrolled,
    CanViewTopicContent, CanPerformEnrolledAction, CanSubmitCourseReview
)
# Assuming a custom IsInstructorRole permission if needed, or using IsAdminUser for now
# from .permissions import IsInstructorRole # Example

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().annotate(course_count=Count('courses')).order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly] # Admin can CRUD, others read-only
    lookup_field = 'slug'
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at', 'course_count']


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all() 
    permission_classes = [AllowAny] # Default, refined per action
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'category__slug': ['exact', 'in'],
        'level': ['exact', 'in'],
        'language': ['exact', 'in'],
        'is_free': ['exact'],
        'instructor__username': ['exact'],
        'tags__slug': ['exact', 'in'], # If you add tags to Course model
    }
    search_fields = ['title', 'slug', 'short_description', 'long_description', 'instructor__full_name', 'category__name']
    ordering_fields = ['title', 'average_rating', 'total_enrollments', 'price', 'created_at', 'published_at', 'total_duration_minutes']
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list': return CourseListSerializer
        if self.action in ['my_courses', 'instructor_courses']: return CourseListSerializer
        return CourseDetailSerializer

    def get_queryset(self):
        user = self.request.user
        base_qs = Course.objects.all()

        # Annotations for current user context
        if user.is_authenticated:
            user_enrollments = Enrollment.objects.filter(user=user, course=OuterRef('pk'))
            user_progress = CourseProgress.objects.filter(user=user, course=OuterRef('pk'))
            
            base_qs = base_qs.annotate(
                _user_is_enrolled=Exists(user_enrollments),
                _user_progress_percentage=Subquery(user_progress.values('progress_percentage')[:1]),
                _user_last_accessed_topic_id=Subquery(user_progress.values('last_accessed_topic_id')[:1])
            ).select_related('category', 'instructor') # Common select_related
        else:
            base_qs = base_qs.select_related('category', 'instructor')

        if self.action == 'retrieve': # For detail view, prefetch more
            qs = base_qs.prefetch_related(
                Prefetch('modules', queryset=Module.objects.order_by('order').prefetch_related(
                    Prefetch('topics', queryset=Topic.objects.order_by('order').prefetch_related(
                        # Prefetch user's progress for each topic if authenticated
                        Prefetch('user_progresses', queryset=TopicProgress.objects.filter(user=user), to_attr='user_topic_progress_for_topic') if user.is_authenticated else 'user_progresses'
                    ))
                )),
                Prefetch('reviews', queryset=CourseReview.objects.select_related('user').order_by('-created_at'))
            )
        else: # For list and other actions
            qs = base_qs

        # Visibility filtering
        if self.action == 'list':
            if user.is_authenticated and user.is_staff:
                return qs.distinct() 
            if user.is_authenticated:
                return qs.filter(Q(is_published=True) | Q(instructor=user)).distinct()
            return qs.filter(is_published=True).distinct()
        
        # For retrieve, object-level permissions will handle unpublished.
        # If user is not staff and not instructor, and course is unpublished, it'll 403/404.
        return qs.distinct()


    def get_permissions(self):
        if self.action == 'create':
            # Feedback: Refine CourseViewSet creation permission
            # Using IsAdminUser, assuming only admins/staff can create course definitions.
            # If non-staff instructors can create, a custom IsInstructorRole permission is needed.
            self.permission_classes = [IsAdminUser]
        elif self.action in ['update', 'partial_update', 'destroy']:
            self.permission_classes = [IsInstructorOrReadOnly]
        elif self.action in ['enroll', 'get_my_progress', 'submit_review']:
            self.permission_classes = [IsAuthenticated] # Specific logic in action methods
        else: # list, retrieve, my_courses, instructor_courses
            self.permission_classes = [AllowAny] 
        return super().get_permissions()

    def perform_create(self, serializer):
        # Instructor is set to the request.user.
        # This implies that any authenticated user (allowed by permission) can create a course and become its instructor.
        # If creation is restricted to IsAdminUser, then request.user will be an admin.
        serializer.save(instructor=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def enroll(self, request, slug=None):
        course = self.get_object() # Permission checks happen here if defined for retrieve
        user = request.user

        if Enrollment.objects.filter(user=user, course=course).exists():
            return Response({'detail': _('You are already enrolled in this course.')}, status=status.HTTP_400_BAD_REQUEST)

        if not course.is_published and not (user.is_staff or course.instructor == user):
            return Response({'detail': _('Cannot enroll in an unpublished course.')}, status=status.HTTP_403_FORBIDDEN)
        
        # Feedback: TODO for payment integration is critical.
        # For now, it correctly blocks enrollment for paid courses.
        if not course.is_free: # Simplified: only allow enrollment if course is free
             # TODO: Integrate with payment system. For now, simulate payment required.
            return Response(
                {'detail': _('This is a paid course. Payment processing is required to enroll.')},
                status=status.HTTP_402_PAYMENT_REQUIRED # Payment Required
            )

        # If course is free or payment is successful (simulated for now)
        enrollment_serializer = EnrollmentSerializer(data={'course_id': course.id}, context={'request': request})
        if enrollment_serializer.is_valid():
            enrollment_serializer.save(user=user) # User set in serializer or here
            return Response({'detail': _('Successfully enrolled in the course.')}, status=status.HTTP_201_CREATED)
        return Response(enrollment_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], url_path='my-courses')
    def my_courses(self, request):
        # Get courses the user is enrolled in
        enrolled_courses_ids = Enrollment.objects.filter(user=request.user).values_list('course_id', flat=True)
        queryset = self.get_queryset().filter(pk__in=enrolled_courses_ids) # Apply common annotations
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], url_path='instructor-courses')
    def instructor_courses(self, request):
        # Assuming IsAdminUser or a specific instructor role for who can be an instructor
        if not request.user.is_staff: # Simplified: only staff can be instructors for this view for now
             return Response({"detail": _("Only instructors can view their courses.")}, status=status.HTTP_403_FORBIDDEN)
        queryset = self.get_queryset().filter(instructor=request.user) # Apply common annotations
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, IsEnrolled], url_path='my-progress')
    def get_my_progress(self, request, slug=None):
        course = self.get_object() # Will apply IsEnrolled permission
        progress = get_object_or_404(
            CourseProgress.objects.select_related('last_accessed_topic__module')
                                 .prefetch_related('topic_progress_entries__topic'),
            user=request.user,
            course=course
        )
        serializer = CourseProgressDetailSerializer(progress, context={'request': request})
        return Response(serializer.data)


class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.all().order_by('order')
    permission_classes = [IsInstructorOrReadOnly] # Default permission

    def get_serializer_class(self):
        if self.action == 'list': return ModuleListSerializer
        return ModuleDetailSerializer

    def get_queryset(self):
        course_slug = self.kwargs.get('course_slug')
        qs = Module.objects.filter(course__slug=course_slug).select_related('course')
        
        # Prefetch topics with user completion status for ModuleDetailSerializer
        if self.action == 'retrieve' and self.request.user.is_authenticated:
            user = self.request.user
            topic_qs = Topic.objects.order_by('order').prefetch_related(
                Prefetch('user_progresses', queryset=TopicProgress.objects.filter(user=user), to_attr='user_topic_progress_for_topic')
            )
            qs = qs.prefetch_related(Prefetch('topics', queryset=topic_qs))
        elif self.action == 'retrieve': # Anonymous or list
            qs = qs.prefetch_related(Prefetch('topics', queryset=Topic.objects.order_by('order')))
        return qs

    def perform_create(self, serializer):
        course_slug = self.kwargs.get('course_slug')
        course = get_object_or_404(Course, slug=course_slug)
        # Check permission against the course object
        self.check_object_permissions(self.request, course)
        serializer.save(course=course)

    def perform_update(self, serializer):
        module_instance = self.get_object()
        self.check_object_permissions(self.request, module_instance.course) # Check against course
        serializer.save() # Course is already linked


class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all().order_by('order')
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list': return TopicListSerializer
        return TopicDetailSerializer

    def get_permissions(self):
        if self.action == 'retrieve':
            self.permission_classes = [CanViewTopicContent] # Allows previewable/free or enrolled/instructor
        elif self.action in ['mark_as_complete', 'submit_quiz_for_topic_action']: # Assuming submit_quiz is action here
            self.permission_classes = [IsAuthenticated, CanPerformEnrolledAction]
        else: # create, update, partial_update, destroy
            self.permission_classes = [IsInstructorOrReadOnly]
        return super().get_permissions()

    def get_queryset(self):
        module_pk = self.kwargs.get('module_pk')
        qs = Topic.objects.filter(module_id=module_pk).select_related('module__course')
        
        if self.action == 'retrieve' and self.request.user.is_authenticated:
             user = self.request.user
             qs = qs.prefetch_related(
                 Prefetch('questions', queryset=Question.objects.order_by('order').prefetch_related('choices')),
                 Prefetch('user_progresses', queryset=TopicProgress.objects.filter(user=user), to_attr='user_topic_progress_for_topic')
             )
        elif self.action == 'retrieve': # Anonymous
             qs = qs.prefetch_related(
                 Prefetch('questions', queryset=Question.objects.order_by('order').prefetch_related('choices'))
             )
        return qs

    def perform_create(self, serializer):
        module_pk = self.kwargs.get('module_pk')
        module_obj = get_object_or_404(Module, pk=module_pk)
        self.check_object_permissions(self.request, module_obj.course) # Check against parent course
        serializer.save(module=module_obj)

    def perform_update(self, serializer):
        topic_instance = self.get_object()
        self.check_object_permissions(self.request, topic_instance.module.course) # Check against course
        serializer.save()

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanPerformEnrolledAction], url_path='mark-complete')
    def mark_as_complete(self, request, course_slug=None, module_pk=None, slug=None):
        topic = self.get_object() # Permission check CanPerformEnrolledAction done by get_object
        user = request.user

        course_progress, _ = CourseProgress.objects.get_or_create(
            user=user,
            course=topic.module.course,
            defaults={ # Ensure enrollment exists if creating progress (should exist due to IsEnrolled check)
                'enrollment': Enrollment.objects.filter(user=user, course=topic.module.course).first()
            }
        )
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=user,
            topic=topic,
            defaults={'course_progress': course_progress, 'is_completed': True}
        )
        if not created and not topic_progress.is_completed:
            topic_progress.is_completed = True
            topic_progress.save() # This will trigger course_progress update via signal
        elif created: # Already saved with is_completed=True, signal would have run
            pass 
            
        return Response(TopicProgressSerializer(topic_progress).data, status=status.HTTP_200_OK)


class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [IsInstructorOrReadOnly]

    def get_queryset(self):
        topic_slug = self.kwargs.get('topic_slug')
        # Prefetch choices for efficiency when serializing questions
        return Question.objects.filter(topic__slug=topic_slug).order_by('order').prefetch_related('choices')

    def perform_create(self, serializer):
        topic_slug = self.kwargs.get('topic_slug')
        topic_obj = get_object_or_404(Topic, slug=topic_slug)
        self.check_object_permissions(self.request, topic_obj.module.course) # Check against course
        serializer.save(topic=topic_obj)

    def perform_update(self, serializer):
        question_instance = self.get_object()
        self.check_object_permissions(self.request, question_instance.topic.module.course) # Check against course
        serializer.save()


class CourseReviewViewSet(viewsets.ModelViewSet):
    serializer_class = CourseReviewSerializer
    permission_classes = [IsAuthenticated] 

    def get_queryset(self):
        course_slug = self.kwargs.get('course_slug')
        # For list action, only return reviews for the specified course.
        # For retrieve/update/delete, DRF uses this queryset to find the object by its PK.
        return CourseReview.objects.filter(course__slug=course_slug).select_related('user', 'course').order_by('-created_at')

    def get_permissions(self):
        if self.action == 'create':
            self.permission_classes = [IsAuthenticated, CanSubmitCourseReview]
        elif self.action in ['update', 'partial_update', 'destroy']:
            # CanSubmitCourseReview also handles ownership for update/delete
            self.permission_classes = [IsAuthenticated, CanSubmitCourseReview] 
        # For list/retrieve, default IsAuthenticated is fine, or AllowAny if reviews are public.
        # For now, keeping IsAuthenticated as base.
        return super().get_permissions()

    def perform_create(self, serializer):
        course_slug = self.kwargs.get('course_slug')
        course = get_object_or_404(Course, slug=course_slug)
        # CanSubmitCourseReview permission checks if user is enrolled and hasn't reviewed this course object
        self.check_object_permissions(self.request, course) 
        serializer.save(user=self.request.user, course=course)


class QuizSubmissionView(generics.CreateAPIView):
    serializer_class = QuizSubmissionSerializer
    permission_classes = [IsAuthenticated] # Further checks (enrollment) in serializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Pass the topic object to the serializer for validation if needed
        # The QuizSubmissionSerializer's validate_topic_id already fetches and stores topic in context
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Permission check for CanPerformEnrolledAction against the topic
        # topic_id is validated, and topic_instance is in serializer.context
        topic_instance = serializer.context.get('topic_instance')
        if not topic_instance: # Should not happen if validate_topic_id worked
             return Response({"detail": "Topic instance not found after validation."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        permission_checker = CanPerformEnrolledAction()
        if not permission_checker.has_object_permission(request, self, topic_instance):
            self.permission_denied(request, message=getattr(permission_checker, 'message', None))

        quiz_attempt = serializer.save() # user is set from context by serializer's create
        result_serializer = QuizAttemptResultSerializer(quiz_attempt, context={'request': request})
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)


class QuizAttemptResultViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for users to view their quiz attempt results.
    """
    serializer_class = QuizAttemptResultSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = QuizAttempt.objects.filter(user=user).select_related(
            'topic__module__course', 'user', 'topic_progress'
        ).prefetch_related(
            # Prefetch answers and their selected choices, and question details for each answer
            Prefetch('answers', queryset=UserTopicAttemptAnswer.objects.select_related('question').prefetch_related('selected_choices', 'question__choices'))
        ).order_by('-submitted_at')
        
        topic_id_param = self.request.query_params.get('topic_id')
        if topic_id_param:
            qs = qs.filter(topic_id=topic_id_param)
        return qs
