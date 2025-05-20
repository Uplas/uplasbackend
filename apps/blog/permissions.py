# apps/blog/permissions.py
from rest_framework import permissions

class IsPostAuthorOrStaffOrReadOnly(permissions.BasePermission):
    """
    Custom permission for BlogPost:
    - Read-only for anyone.
    - Edit/Delete only by the post's 'author' (Uplas User) or staff.
    """
    def has_object_permission(self, request, view, obj): # obj is a BlogPost instance
        if request.method in permissions.SAFE_METHODS:
            return True
        
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_staff: # Staff can edit/delete any post
            return True
        
        # Check if the request.user is the author of the post
        # This assumes obj.author is the ForeignKey to the User model.
        # If using author_profile_override linked to a User, logic might need to check that too.
        return hasattr(obj, 'author') and obj.author == request.user

class IsCommentAuthorOrStaffOrReadOnly(permissions.BasePermission):
    """
    Custom permission for BlogComment:
    - Read-only for anyone (approved comments).
    - Edit/Delete only by the comment's 'author' (Uplas User) or staff.
    - Guest comments (where author is None) cannot be edited/deleted by non-staff.
    """
    def has_object_permission(self, request, view, obj): # obj is a BlogComment instance
        if request.method in permissions.SAFE_METHODS:
            return True # Visibility of comment itself is controlled by is_approved

        if not request.user or not request.user.is_authenticated:
            return False
            
        if request.user.is_staff: # Staff can edit/delete any comment
            return True
        
        # If comment has a linked Uplas author, only that author can edit/delete
        if obj.author:
            return obj.author == request.user
        
        # If it's a guest comment (obj.author is None), only staff can modify (already covered by staff check)
        return False
