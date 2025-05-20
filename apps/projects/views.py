from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction, models

from rest_framework import viewsets, status, permissions, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError

from .models import ProjectCategory, ProjectTag, Project, UserProject
from .serializers import (
    ProjectCategorySerializer, ProjectTagSerializer, ProjectSerializer,
    UserProjectSerializer, UserProjectStartSerializer, UserProjectSubmitSerializer
)
# Assuming AI Project Generator Agent has an API client or function
# from ..ai_agents.project_generator_client import request_project_assessment, suggest_new_project

class ProjectCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for listing project categories.
    /api/projects/categories/ 
    """
    queryset = ProjectCategory.objects.all()
    serializer_class = ProjectCategorySerializer
    permission_classes = [permissions.AllowAny]

class ProjectTagViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for listing project tags.
    (Implied, useful for filtering)
    """
    queryset = ProjectTag.objects.all()
    serializer_class = ProjectTagSerializer
    permission_classes = [permissions.AllowAny]

class ProjectViewSet(viewsets.ReadOnlyModelViewSet): # Platform projects are generally read-only by users
    """
    API endpoint for listing and retrieving available projects.
    /api/projects/ 
    /api/projects/{project_slug}/ 
    """
    queryset = Project.objects.filter(is_published=True).select_related('category', 'created_by').prefetch_related('tags', 'associated_courses')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtering
        category_slug = self.request.query_params.get('category')
        tag_slugs = self.request.query_params.getlist('tag') # ?tag=python&tag=api
        difficulty = self.request.query_params.get('difficulty')
        search_term = self.request.query_params.get('search')

        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        if tag_slugs:
            queryset = queryset.filter(tags__slug__in=tag_slugs).distinct()
        if difficulty:
            queryset = queryset.filter(difficulty_level=difficulty)
        if search_term:
            queryset = queryset.filter(
                models.Q(title__icontains=search_term) |
                models.Q(subtitle__icontains=search_term) |
                models.Q(description_html__icontains=search_term) |
                models.Q(tags__name__icontains=search_term)
            ).distinct()
            
        return queryset

    @action(detail=False, methods=['get'], url_path='suggestions', permission_classes=[permissions.IsAuthenticated])
    def suggestions(self, request):
        """
        Endpoint for AI-powered project suggestions.
        /api/projects/suggestions/ 
        This would call the AI Project Generator agent.
        """
        user = request.user
        # TODO: Call AI Project Generator Agent
        # ai_suggested_projects_data = suggest_new_project(user_profile=user.profile) # Assuming user.profile has relevant data
        
        # For now, returning some featured or recent platform projects as placeholder
        suggested_projects = Project.objects.filter(is_published=True, is_featured=True).order_by('?')[:5] # Random 5 featured
        if not suggested_projects.exists():
            suggested_projects = Project.objects.filter(is_published=True).order_by('-created_at')[:5]

        serializer = self.get_serializer(suggested_projects, many=True, context={'request': request})
        return Response(serializer.data)

    # Admin/AI might need to POST to /api/projects/ to create new projects
    # For that, this ViewSet would not be ReadOnlyModelViewSet.
    # def perform_create(self, serializer):
    #     # If an AI agent is creating, it might not have a user session.
    #     # Or, use a dedicated service account or specific auth for AI agent.
    #     serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None, project_source='ai_generated')


class UserProjectViewSet(viewsets.ModelViewSet): # Allows create (start), retrieve, update (submit), list
    """
    API endpoint for managing user's projects (their instances/attempts).
    List user's projects: /api/projects/my-projects/ (maps to list action here)
    Start a project: (POST to this viewset with project_id, creating a UserProject instance)
    Retrieve a user's project: /api/projects/my-projects/{user_project_id}/
    """
    serializer_class = UserProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only see their own UserProject instances
        return UserProject.objects.filter(user=self.request.user).select_related(
            'project__category', 'project__created_by', 'user'
        ).prefetch_related('project__tags', 'project__associated_courses').order_by('-last_accessed_at')

    def perform_create(self, serializer):
        # This is called when a user "starts" a project.
        # The project_id should be in the request data.
        project_id = serializer.validated_data.get('project').id # project comes from validated_data
        project = get_object_or_404(Project, id=project_id, is_published=True)

        # Check if UserProject already exists
        if UserProject.objects.filter(user=self.request.user, project=project).exists():
            raise DRFValidationError(_("You have already started this project."))
        
        serializer.save(user=self.request.user, project=project, status='active', started_at=timezone.now())

    # Custom action to "start" a project if preferred over direct POST to list endpoint
    @action(detail=False, methods=['post'], url_path='start-project', serializer_class=serializers.DictField) # Expects {"project_id": "uuid"}
    def start_project(self, request):
        """
        Explicit endpoint to start a project.
        POST /api/projects/my-projects/start-project/
        Body: { "project_id": "..." }
        /api/projects/{project_slug}/start/ - this maps here conceptually.
        """
        project_id = request.data.get('project_id')
        if not project_id:
            return Response({'detail': 'project_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        project = get_object_or_404(Project, id=project_id, is_published=True)
        user = request.user

        user_project, created = UserProject.objects.get_or_create(
            user=user,
            project=project,
            defaults={'status': 'active', 'started_at': timezone.now()}
        )

        if not created and user_project.status == 'not_started': # If it existed as 'not_started'
            user_project.status = 'active'
            user_project.started_at = timezone.now()
            user_project.save()
        elif not created: # Already started or in another state
             return Response({'detail': _(f"You have already an instance of this project with status: {user_project.get_status_display()}.")}, status=status.HTTP_400_BAD_REQUEST)

        serializer = UserProjectSerializer(user_project, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


    @action(detail=True, methods=['post'], url_path='submit', serializer_class=UserProjectSubmitSerializer)
    def submit_project(self, request, pk=None):
        """
        Endpoint for user to submit their project for assessment.
        POST /api/projects/my-projects/{user_project_id}/submit/
        /api/projects/{project_slug}/submit/ maps here. pk is UserProject id.
        """
        user_project = self.get_object() # Ensures it's the user's own project
        
        if user_project.status not in ['active', 'completed_failed']: # Can resubmit if failed
            return Response({'detail': _(f"Project cannot be submitted with status: {user_project.get_status_display()}")}, status=status.HTTP_400_BAD_REQUEST)

        submit_serializer = self.get_serializer(data=request.data)
        submit_serializer.is_valid(raise_exception=True)
        submission_data = submit_serializer.validated_data

        with transaction.atomic():
            user_project.status = 'submitted'
            user_project.submitted_at = timezone.now()
            # Save submission data
            if 'submission_files' in submission_data:
                user_project.submission_data_json = {'files': submission_data['submission_files']}
            elif 'repository_url' in submission_data:
                user_project.project_repository_url = submission_data['repository_url']
                user_project.submission_data_json = {'repository_url': submission_data['repository_url']} # Also store in JSON if preferred
            elif 'submission_data' in submission_data:
                 user_project.submission_data_json = submission_data['submission_data']

            user_project.save()

            # TODO: Trigger AI Assessment Agent
            # assessment_result = request_project_assessment(
            #     user_project_id=user_project.id,
            #     project_spec=user_project.project.ai_generated_spec_json or user_project.project.description_html,
            #     submission_data=user_project.submission_data_json or user_project.project_repository_url
            # )
            # This call would be asynchronous, and the AI agent would update the UserProject via another API endpoint or callback.
            # For now, we'll simulate an immediate response or a pending state.
            
            # Placeholder: If assessment is synchronous and fast (unlikely for complex AI)
            # user_project.assessment_score = assessment_result.get('score')
            # user_project.assessment_feedback_html = assessment_result.get('feedback')
            # if user_project.assessment_score >= 75:
            #     user_project.status = 'completed_passed'
            # else:
            #     user_project.status = 'completed_failed'
            #     # TODO: Trigger AI Tutor with context (user_project.id, assessment_feedback_html)
            # user_project.completed_at = timezone.now()
            # user_project.save()

        return Response(
            UserProjectSerializer(user_project, context={'request': request}).data,
            status=status.HTTP_200_OK
        )

    # Endpoint for AI Agent to post assessment results
    @action(detail=True, methods=['post'], url_path='update-assessment', permission_classes=[permissions.AllowAny]) # Or a specific service account permission
    def update_assessment_results(self, request, pk=None):
        # This endpoint should be secured, e.g., IP whitelist, secret key, or service account auth
        user_project = get_object_or_404(UserProject, pk=pk)
        
        score = request.data.get('assessment_score')
        feedback_html = request.data.get('assessment_feedback_html')
        # raw_ai_output = request.data.get('ai_assessment_details_json') # Optional

        if score is None or feedback_html is None:
            return Response({'detail': 'assessment_score and assessment_feedback_html are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            score = float(score)
            if not (0 <= score <= 100):
                raise ValueError("Score out of range")
        except ValueError:
             return Response({'detail': 'Invalid assessment_score value.'}, status=status.HTTP_400_BAD_REQUEST)


        with transaction.atomic():
            user_project.assessment_score = score
            user_project.assessment_feedback_html = feedback_html
            # user_project.ai_assessment_details_json = raw_ai_output
            user_project.completed_at = timezone.now()

            if score >= 75:
                user_project.status = 'completed_passed'
            else:
                user_project.status = 'completed_failed'
                # TODO: Trigger AI Tutor. This could be a signal handler on UserProject save
                # or an explicit call here if the AI Tutor has an API.
                # trigger_ai_tutor(user_id=user_project.user.id, project_id=user_project.project.id,
                #                  user_project_id=user_project.id, feedback=feedback_html)
                print(f"AI Tutor should be triggered for UserProject {user_project.id} due to score {score}")

            user_project.save()
        
        return Response({'status': 'assessment updated'}, status=status.HTTP_200_OK)
