from rest_framework.permissions import BasePermission, SAFE_METHODS, IsAdminUser
from .models import Forum, Thread, Post, Comment, Like, Report # Ensure correct import path

# IsAdminUser is a built-in DRF permission.
# IsAuthenticated is also built-in.

class IsAdminOrReadOnly(BasePermission):
    """
    Allows read-only access to any request, including unauthenticated users.
    Allows write access (POST, PUT, PATCH, DELETE) only to admin users.
    Useful for models like Forum where viewing is public but management is admin-only.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


class IsAuthorOrReadOnly(BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `author` attribute.
    Read-only access is granted to any request (authenticated or not),
    unless combined with other permissions like IsAuthenticated.
    """
    message = "You do not have permission to edit or delete this content as you are not the author."

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in SAFE_METHODS:
            return True

        # Write permissions are only allowed to the author of the content or staff.
        if not request.user.is_authenticated:
            return False
        
        # Staff/admins can edit/delete anything
        if request.user.is_staff:
            return True
            
        # Check if the object has an 'author' attribute and if it matches the request user.
        # This works for Thread, Post, Comment if they have an 'author' field.
        return hasattr(obj, 'author') and obj.author == request.user


class CanCreateThreadOrPost(BasePermission):
    """
    Permission to check if a user can create a new thread in a forum
    or a new post (reply) in a thread.
    - User must be authenticated.
    - For Threads: Forum must not be restricted in a way that prevents new threads (if such logic exists).
    - For Posts: Thread must not be closed.
    """
    message = "You do not have permission to create content here at this time."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            self.message = "You must be logged in to create threads or posts."
            return False
        return True # Further checks might be needed based on view context

    def has_object_permission(self, request, view, obj):
        # This permission is more about "can this user post TO this object (Forum/Thread)?"
        # It's often better handled at the view level before object creation,
        # or by checking the parent object if this permission is applied to the parent.

        if not request.user.is_authenticated:
            self.message = "You must be logged in to create threads or posts."
            return False

        if isinstance(obj, Forum): # Checking if user can create a Thread in this Forum
            # Add any specific forum-level restrictions here if needed
            # e.g., if forum.can_users_create_threads is False
            return True # Assuming any authenticated user can create a thread in any forum for now

        if isinstance(obj, Thread): # Checking if user can create a Post (reply) in this Thread
            if obj.is_closed:
                self.message = "This thread is closed and no longer accepts replies."
                return False
            if obj.is_hidden and not request.user.is_staff: # Only staff can reply to hidden threads
                self.message = "This thread is currently hidden."
                return False
            return True
        
        return False # Should not apply to other object types directly for creation


class IsModeratorOrAdmin(BasePermission):
    """
    Allows access only to users who are staff/admin or designated moderators.
    For actions like pinning/closing threads, hiding content, managing reports.
    (A more complex system might have a specific 'Moderator' role or group).
    For now, we'll equate moderators with staff/admin users.
    """
    message = "You do not have moderator privileges to perform this action."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        # Object-level check might not be strictly necessary if has_permission is sufficient,
        # but can be used for finer-grained control if needed.
        return request.user and request.user.is_authenticated and request.user.is_staff


class CanInteractWithContent(BasePermission):
    """
    Permission for actions like Liking or Reporting content.
    User must be authenticated.
    The content itself (Thread, Post, Comment) should not be hidden from the user.
    """
    message = "You must be logged in to interact with content."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # obj is the content being liked/reported (Thread, Post, Comment)
        if not request.user.is_authenticated:
            return False

        if hasattr(obj, 'is_hidden') and obj.is_hidden:
            # Allow staff to interact with hidden content, but not regular users
            return request.user.is_staff
        
        # If it's a Post or Comment, also check if its parent Thread is hidden
        parent_thread = None
        if isinstance(obj, Post):
            parent_thread = obj.thread
        elif isinstance(obj, Comment):
            parent_thread = obj.post.thread
        
        if parent_thread and parent_thread.is_hidden:
            return request.user.is_staff
            
        return True


class CanManageReport(BasePermission):
    """
    Permission for viewing details of a report or updating its status.
    Restricted to staff/admin users.
    """
    message = "You do not have permission to manage reports."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        # obj is a Report instance
        return request.user and request.user.is_authenticated and request.user.is_staff


