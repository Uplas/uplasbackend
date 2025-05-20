from rest_framework import permissions
from .models import CommunityGroup, GroupMembership, CommunityPost, PostComment # Ensure models are imported

class IsAuthorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow authors of an object to edit it.
    Read-only for everyone else.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        # Check if the obj has an 'author' attribute and if it matches the request user
        return hasattr(obj, 'author') and obj.author == request.user

class IsGroupAdminOrCreatorOrReadOnly(permissions.BasePermission):
    """
    Permission for CommunityGroup:
    - Read-only for anyone (respecting group's is_private status, handled in view).
    - Edit/Delete only by the group creator or a group admin.
    """
    def has_object_permission(self, request, view, obj: CommunityGroup):
        if request.method in permissions.SAFE_METHODS:
            # View-level logic in get_object or get_queryset should handle is_private visibility
            return True
        
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user is the creator
        if obj.creator == request.user:
            return True
        
        # Check if user is an admin of the group
        try:
            membership = GroupMembership.objects.get(user=request.user, group=obj)
            return membership.role == 'admin'
        except GroupMembership.DoesNotExist:
            return False
        return False

class CanPostInGroup(permissions.BasePermission):
    """
    Permission to check if a user can create a post within a specific group.
    Typically, must be a member. Admins/Moderators of the group can also post.
    """
    def has_object_permission(self, request, view, obj: CommunityGroup): # obj is the group
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Staff can always post (e.g., for announcements)
        if request.user.is_staff:
            return True
            
        try:
            membership = GroupMembership.objects.get(user=request.user, group=obj)
            # Allow members, admins, and moderators to post
            return membership.role in ['member', 'admin', 'moderator']
        except GroupMembership.DoesNotExist:
            # If group is public and allows non-member posting (less common, configure if needed)
            # if not obj.is_private and getattr(settings, 'ALLOW_NON_MEMBER_GROUP_POSTING', False):
            #    return True
            return False


class CanCommentOnPost(permissions.BasePermission):
    """
    Permission to check if a user can comment on a post.
    Generally, if they can view the post and it's not closed.
    """
    def has_object_permission(self, request, view, obj: CommunityPost): # obj is the CommunityPost
        if obj.is_closed:
            return False # Cannot comment if post is closed
        
        # If post is in a private group, user must be a member of that group to comment
        if obj.group and obj.group.is_private:
            if not request.user or not request.user.is_authenticated:
                return False
            if not obj.group.members.filter(id=request.user.id).exists():
                return False # Not a member of the private group containing the post
                
        return True # If public post, or public group post, or member of private group's post

class CanManageGroupMembership(permissions.BasePermission):
    """
    Permission to manage group members (e.g., remove member, change role).
    Only for group admins or the group creator.
    """
    def has_object_permission(self, request, view, obj: CommunityGroup): # obj is the group
        if not request.user or not request.user.is_authenticated:
            return False
        if obj.creator == request.user:
            return True
        try:
            membership = GroupMembership.objects.get(user=request.user, group=obj)
            return membership.role == 'admin'
        except GroupMembership.DoesNotExist:
            return False
        return False
