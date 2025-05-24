from rest_framework.permissions import BasePermission, SAFE_METHODS, IsAdminUser
from .models import BlogPost, BlogComment # Assuming models are in the same app

# IsAdminUser is a built-in DRF permission.
# IsAuthenticated is also built-in.

class IsAdminOrReadOnly(BasePermission):
    """
    Allows read-only access to any request, including unauthenticated users.
    Allows write access (POST, PUT, PATCH, DELETE) only to admin/staff users.
    Useful for models like BlogCategory and BlogPostTag.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


class IsAuthorOrAdminOrReadOnlyForBlogPost(BasePermission):
    """
    Permission for BlogPost objects.
    - Read access:
        - Published posts: Allowed for anyone.
        - Draft/Archived posts: Allowed only for the author or admin/staff.
    - Write access (create, update, delete):
        - Create: Allowed for authenticated users (view might restrict further based on roles).
        - Update/Delete: Allowed only for the author of the post or admin/staff.
    """
    message = "You do not have permission to perform this action on this blog post."

    def has_permission(self, request, view):
        # For list view, allow any (queryset will be filtered).
        # For create (POST), user must be authenticated.
        if view.action == 'create':
            return request.user and request.user.is_authenticated
        return True # Let has_object_permission handle retrieve/update/delete

    def has_object_permission(self, request, view, obj):
        # obj is a BlogPost instance
        if not isinstance(obj, BlogPost):
            return False

        # Read permissions (GET, HEAD, OPTIONS)
        if request.method in SAFE_METHODS:
            if obj.status == 'published':
                return True
            # For draft/archived posts, only author or staff can view
            return request.user.is_authenticated and (obj.author == request.user or request.user.is_staff)

        # Write permissions (PUT, PATCH, DELETE)
        if not request.user.is_authenticated:
            return False
        
        # Only admin/staff or the author can modify/delete
        return obj.author == request.user or request.user.is_staff


class IsCommentAuthorOrAdminOrReadOnly(BasePermission):
    """
    Permission for BlogComment objects.
    - Read access:
        - Approved and publicly visible comments: Allowed for anyone.
        - Hidden/unapproved comments: Allowed only for author or admin/staff.
    - Write access (update, delete):
        - Allowed only for the author of the comment or admin/staff.
    - Create access is handled by CanCommentOnPublicPost.
    """
    message = "You do not have permission to perform this action on this comment."

    def has_object_permission(self, request, view, obj):
        # obj is a BlogComment instance
        if not isinstance(obj, BlogComment):
            return False

        # Read permissions
        if request.method in SAFE_METHODS:
            if obj.is_publicly_visible: # Uses the model property
                return True
            # For non-public comments, only author or staff can view
            return request.user.is_authenticated and (obj.author == request.user or request.user.is_staff)

        # Write permissions
        if not request.user.is_authenticated:
            return False
        
        return obj.author == request.user or request.user.is_staff


class CanCommentOnPublicPost(BasePermission):
    """
    Permission to check if a user can create a comment on a specific BlogPost.
    - User must be authenticated.
    - BlogPost must be 'published'.
    - (Future: BlogPost might have a 'comments_enabled' flag).
    This is typically checked at the view level when creating a comment,
    or as an object permission on the BlogPost when the action is 'create_comment'.
    """
    message = "You cannot comment on this blog post at this time."

    def has_permission(self, request, view): # General check for authenticated user
        if not request.user or not request.user.is_authenticated:
            self.message = "You must be logged in to comment."
            return False
        return True

    def has_object_permission(self, request, view, obj): # obj is the BlogPost instance
        if not request.user or not request.user.is_authenticated:
            self.message = "You must be logged in to comment."
            return False
            
        if not isinstance(obj, BlogPost):
            # This permission is meant to be checked against a BlogPost object
            return False 

        if obj.status != 'published':
            self.message = "Comments are only allowed on published blog posts."
            return False
        
        # Add other conditions if needed (e.g., if obj.are_comments_closed)
        return True


class IsBlogModerator(BasePermission): # Essentially IsAdminUser for now
    """
    Allows access only to users who are staff/admin (acting as blog moderators).
    For actions like approving comments, changing post status beyond author's capability.
    """
    message = "You do not have blog moderator privileges."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        return request.user and request.user.is_authenticated and request.user.is_staff

