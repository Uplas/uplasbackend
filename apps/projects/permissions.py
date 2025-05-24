from rest_framework.permissions import BasePermission, SAFE_METHODS, IsAdminUser
from .models import Project, UserProject, ProjectSubmission, ProjectAssessment, ProjectTag
# Assuming your custom User model might have an 'is_instructor' flag or similar role system.
# from django.contrib.auth import get_user_model
# User = get_user_model()

class IsAdminOrReadOnlyForTags(BasePermission):
    """
    Allows read-only access for ProjectTags to any user.
    Allows write access only to admin users.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


class IsProjectCreatorOrAdminOrReadOnly(BasePermission):
    """
    Allows read access to published projects for anyone.
    Allows read access to unpublished projects only for creator or admin.
    Allows write access (create, update, delete) only to the creator of the project
    definition or admin users.
    'creator' refers to the 'created_by' field on the Project model.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True # List/retrieve access initially allowed, object permission will refine for unpublished
        # For POST (create), user must be authenticated (and potentially an instructor/admin)
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # obj is a Project instance
        if not isinstance(obj, Project):
            return False

        # Read permissions:
        if request.method in SAFE_METHODS:
            if obj.is_published:
                return True
            # Unpublished projects can only be seen by their creator or admin/staff
            return request.user.is_authenticated and (obj.created_by == request.user or request.user.is_staff)

        # Write permissions:
        if not request.user.is_authenticated:
            return False
        
        # Only admin or the original creator (if defined) can modify/delete
        # If created_by is None (e.g., AI generated and no specific user assigned), only admin can modify.
        if request.user.is_staff:
            return True
        if obj.created_by and obj.created_by == request.user:
            return True
            
        return False


class IsUserProjectOwner(BasePermission):
    """
    Allows access only to the user who owns the UserProject instance or admins.
    """
    message = "You do not have permission to access or modify this user project."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        if not isinstance(obj, UserProject):
            return False

        if request.user.is_staff: # Admins can access any UserProject
            return True
        
        return obj.user == request.user


class CanSubmitToUserProject(BasePermission):
    """
    Allows a user to create a ProjectSubmission if they own the related UserProject
    and the UserProject is in an appropriate status (e.g., 'in_progress' or 'failed').
    """
    message = "You cannot submit to this project at this time or do not own it."

    def has_permission(self, request, view):
        # This permission is typically checked at the view level before creating a submission.
        # It needs context about which UserProject the submission is for.
        if not request.user.is_authenticated:
            return False
        
        user_project_id = view.kwargs.get('user_project_pk') or request.data.get('user_project')
        if not user_project_id:
            # Cannot determine the user_project, deny. View should provide this.
            return False 
            
        try:
            user_project = UserProject.objects.select_related('user').get(pk=user_project_id)
        except UserProject.DoesNotExist:
            return False # UserProject not found

        if user_project.user != request.user and not request.user.is_staff:
            return False # Not the owner and not admin

        # Allow submission if project is 'in_progress' or 'failed' (allowing re-submission)
        # Admins might bypass this status check for testing/management.
        if request.user.is_staff:
            return True
            
        return user_project.status in ['in_progress', 'failed', 'submitted'] # 'submitted' if re-submission is allowed before assessment
        
    def has_object_permission(self, request, view, obj):
        # For viewing/deleting own submissions
        if not request.user.is_authenticated:
            return False
            
        if not isinstance(obj, ProjectSubmission):
            return False

        if request.user.is_staff:
            return True
        
        return obj.user_project.user == request.user


class IsAssessmentViewerOrAdmin(BasePermission):
    """
    Allows viewing ProjectAssessment if:
    - User is the owner of the UserProject related to the submission.
    - User is an admin or staff.
    - User is the manual_assessor (if any).
    Write access (create/update) is typically for AI agents or admins/instructors.
    """
    message = "You do not have permission to view this project assessment."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if not isinstance(obj, ProjectAssessment):
            return False

        if request.user.is_staff:
            return True
        
        # Owner of the UserProject (via submission) can view their assessment
        if obj.submission.user_project.user == request.user:
            return True
        
        # Manual assessor can view
        if obj.manual_assessor and obj.manual_assessor == request.user:
            return True
            
        return False


class CanManageProjectAssessment(BasePermission):
    """
    Permission for creating/updating ProjectAssessments.
    Typically restricted to admin/staff or a designated AI service role.
    For simplicity, we'll restrict to staff here.
    A more complex system might use API keys or service accounts for AI.
    """
    message = "You do not have permission to create or modify project assessments."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # Only staff/admins can create or update assessments through this API.
        # AI agent would use a different mechanism or a service account.
        return request.user.is_staff

    def has_object_permission(self, request, view, obj):
        # If allowing updates/deletes by staff
        if not request.user.is_authenticated:
            return False
        return request.user.is_staff
