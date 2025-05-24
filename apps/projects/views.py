from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Q

from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser

# Django Filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import (
    ProjectTag, Project, UserProject, ProjectSubmission, ProjectAssessment
)
from .serializers import (
    ProjectTagSerializer,
    ProjectListSerializer, ProjectDetailSerializer,
    UserProjectListSerializer, UserProjectDetailSerializer,
    ProjectSubmissionSerializer,
    ProjectAssessmentSerializer
)
from .permissions import (
    IsAdminOrReadOnlyForTags, IsProjectCreatorOrAdminOrReadOnly,
    IsUserProjectOwner, CanSubmitToUserProject,
    IsAssessmentViewerOrAdmin, CanManageProjectAssessment
)

class ProjectTagViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing project tags.
    Admin users can create, update, delete. All users can list and retrieve.
    """
    queryset = ProjectTag.objects.all().order_by('name')
    serializer_class = ProjectTagSerializer
    permission_classes = [IsAdminOrReadOnlyForTags]
    lookup_field = 'slug'
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']


class ProjectViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing project definitions.
    - List/Retrieve: Published projects are visible to all. Unpublished only to creator/admin.
    - Create/Update/Delete: Restricted to project creator or admin.
    """
    queryset = Project.objects.all() # Base queryset
    permission_classes = [IsProjectCreatorOrAdminOrReadOnly] # Handles most cases
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'difficulty_level': ['exact', 'in'],
        'technologies_used__slug': ['exact', 'in'],
        'ai_generated': ['exact'],
        'created_by__username': ['exact'],
    }
    search_fields = ['title', 'description', 'technologies_used__name']
    ordering_fields = ['title', 'difficulty_level', 'estimated_duration_hours', 'created_at', 'updated_at']
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return ProjectListSerializer
        return ProjectDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.is_staff:
            return Project.objects.all().select_related('created_by').prefetch_related('technologies_used')
        
        # For list view, show published OR user's own unpublished projects
        if self.action == 'list' and user.is_authenticated:
            return Project.objects.filter(
                Q(is_published=True) | Q(created_by=user)
            ).select_related('created_by').prefetch_related('technologies_used').distinct()
        
        # For retrieve, permissions will handle unpublished. Default to published for anonymous.
        if self.action == 'retrieve' or not user.is_authenticated:
             return Project.objects.filter(is_published=True).select_related('created_by').prefetch_related('technologies_used')

        # Default for authenticated users (e.g. if they are trying to access a direct non-list/retrieve action)
        return Project.objects.filter(is_published=True).select_related('created_by').prefetch_related('technologies_used')


    def perform_create(self, serializer):
        # If created_by is not in serializer (e.g. not admin setting it), set to current user.
        # Serializer's create method already handles this logic.
        serializer.save() # created_by is handled in serializer context

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='start-project', url_name='start-project')
    def start_project(self, request, slug=None):
        """
        Allows an authenticated user to start a project (creates a UserProject instance).
        """
        project_definition = self.get_object() # Gets the Project instance, permission checks done

        if not project_definition.is_published:
            return Response({'detail': _('This project is not published and cannot be started.')}, status=status.HTTP_400_BAD_REQUEST)

        # UserProjectDetailSerializer handles validation for existing UserProject
        user_project_data = {'project_id': project_definition.id, 'status': 'in_progress'}
        context = {'request': request}
        user_project_serializer = UserProjectDetailSerializer(data=user_project_data, context=context)

        if user_project_serializer.is_valid():
            user_project = user_project_serializer.save(user=request.user) # Explicitly pass user
            return Response(UserProjectDetailSerializer(user_project, context=context).data, status=status.HTTP_201_CREATED)
        return Response(user_project_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserProjectViewSet(viewsets.ModelViewSet):
    """
    API endpoint for users to manage their instances of projects.
    - Users can list/retrieve/update their own UserProjects.
    - Admins can manage all UserProjects.
    """
    serializer_class = UserProjectDetailSerializer # Detail for retrieve/update
    permission_classes = [IsAuthenticated, IsUserProjectOwner] # IsUserProjectOwner for object-level

    def get_queryset(self):
        user = self.request.user
        if user.is_staff: # Admins see all
            return UserProject.objects.all().select_related('user', 'project__created_by').prefetch_related('project__technologies_used')
        # Regular users see only their own projects
        return UserProject.objects.filter(user=user).select_related('user', 'project__created_by').prefetch_related('project__technologies_used')

    def get_serializer_class(self):
        if self.action == 'list':
            return UserProjectListSerializer
        return UserProjectDetailSerializer

    def perform_create(self, serializer):
        # Creation typically via ProjectViewSet's 'start-project' action.
        # If direct creation is allowed here, ensure project_id is validated and user is set.
        # This assumes 'project_id' is in validated_data.
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        # User can update fields like repository_url, live_url, or status (e.g., to 'in_progress')
        # Ensure they can't change the 'user' or 'project' fields after creation.
        # Serializer read_only_fields should handle this.
        # If status is changed to 'in_progress', model's save method handles started_at.
        user_project = serializer.save()
        if 'status' in serializer.validated_data and serializer.validated_data['status'] == 'in_progress' and not user_project.started_at:
            user_project.started_at = timezone.now()
            user_project.save(update_fields=['started_at'])


class ProjectSubmissionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing project submissions.
    - Users can create submissions for their UserProjects.
    - Users can list/retrieve their own submissions.
    - Admins/Instructors might view submissions related to projects they manage.
    """
    serializer_class = ProjectSubmissionSerializer
    permission_classes = [IsAuthenticated, CanSubmitToUserProject] # CanSubmitToUserProject for create and object-level

    def get_queryset(self):
        user = self.request.user
        # Filter by user_project_pk from URL if provided (for nested routes)
        user_project_pk = self.kwargs.get('user_project_pk')

        if user.is_staff: # Admins see all (or all for a specific user_project if nested)
            if user_project_pk:
                return ProjectSubmission.objects.filter(user_project_id=user_project_pk).select_related('user_project__user', 'user_project__project')
            return ProjectSubmission.objects.all().select_related('user_project__user', 'user_project__project')
        
        # Regular users see only their own submissions
        base_qs = ProjectSubmission.objects.filter(user_project__user=user)
        if user_project_pk:
            return base_qs.filter(user_project_id=user_project_pk).select_related('user_project__user', 'user_project__project')
        return base_qs.select_related('user_project__user', 'user_project__project')

    def perform_create(self, serializer):
        user_project_id = serializer.validated_data['user_project'].id # From source='user_project'
        user_project = get_object_or_404(UserProject, id=user_project_id, user=self.request.user)
        
        # CanSubmitToUserProject permission class already checks if user can submit to this user_project.
        # The permission class uses view.kwargs.get('user_project_pk') or request.data.get('user_project')
        # Ensure the permission has access to the user_project object for its checks.
        # Here, we explicitly check ownership again for safety before saving.
        if user_project.user != self.request.user:
             raise PermissionDenied(_("You can only submit to your own assigned projects."))

        # Model's save() method handles updating UserProject status to 'submitted' and versioning.
        serializer.save() # user_project is already set in validated_data

    # Update/Delete of submissions might be restricted, especially after assessment.
    # Current CanSubmitToUserProject allows owner to delete/update their own.


class ProjectAssessmentViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing project assessments.
    - Users can retrieve assessments for their submissions.
    - Admins/AI can create/update assessments.
    """
    queryset = ProjectAssessment.objects.all().select_related(
        'submission__user_project__user',
        'submission__user_project__project',
        'manual_assessor'
    )
    serializer_class = ProjectAssessmentSerializer
    # Permissions are more nuanced here
    # Create/Update: CanManageProjectAssessment (Admins/Staff/AI Service Role)
    # Retrieve/List: IsAssessmentViewerOrAdmin (User who owns project, Assessor, Admin)

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), CanManageProjectAssessment()]
        # For list/retrieve
        return [IsAuthenticated(), IsAssessmentViewerOrAdmin()] # IsAssessmentViewerOrAdmin is object-level

    def get_queryset(self):
        user = self.request.user
        # Filter by submission_pk from URL if provided (for nested routes)
        submission_pk = self.kwargs.get('submission_pk')

        if user.is_staff: # Admins see all
            if submission_pk:
                return ProjectAssessment.objects.filter(submission_id=submission_pk)
            return ProjectAssessment.objects.all()
        
        # Regular users see only assessments for their own project submissions
        # Or if they are a manual assessor (though less common for listing all they assessed)
        base_qs = ProjectAssessment.objects.filter(
            Q(submission__user_project__user=user) | Q(manual_assessor=user)
        ).distinct()

        if submission_pk:
            return base_qs.filter(submission_id=submission_pk)
        return base_qs

    def perform_create(self, serializer):
        # AI agent or Admin creates this.
        # Serializer's create method can handle setting manual_assessor if applicable.
        # Model's save() method handles updating UserProject status.
        serializer.save()

    def perform_update(self, serializer):
        # Model's save() method handles updating UserProject status.
        serializer.save()

    # Custom action for AI to submit assessment (could be a separate endpoint too)
    @action(detail=False, methods=['post'], permission_classes=[CanManageProjectAssessment], # Or a specific AI service permission
            url_path='submit-ai-assessment', url_name='submit-ai-assessment')
    def submit_ai_assessment(self, request):
        """
        An endpoint specifically for an AI agent to submit an assessment.
        Expects submission_id and assessment data.
        """
        serializer = self.get_serializer(data=request.data, context={'request': request}) # ProjectAssessmentSerializer
        if serializer.is_valid():
            # Ensure AI details are set if not in payload but implied by endpoint
            if 'assessed_by_ai' not in serializer.validated_data:
                 serializer.validated_data['assessed_by_ai'] = True
            # if 'assessor_ai_agent_name' not in serializer.validated_data and hasattr(settings, 'DEFAULT_AI_ASSESSOR_NAME'):
            #      serializer.validated_data['assessor_ai_agent_name'] = settings.DEFAULT_AI_ASSESSOR_NAME
            
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

