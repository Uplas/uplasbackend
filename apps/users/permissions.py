from rest_framework.permissions import BasePermission, SAFE_METHODS, IsAdminUser
from django.utils.translation import gettext_lazy as _

# IsAdminUser and IsAuthenticated are built-in DRF permissions.

class IsAccountOwnerOrReadOnly(BasePermission):
    """
    Allows read-only access to any authenticated user for user/profile information.
    Allows write access (update, partial_update, delete) only to the owner of the account
    or admin users.
    This is typically used for UserProfile views or User views where users manage themselves.
    """
    message = _("You do not have permission to modify this user account or profile.")

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request if they are authenticated,
        # so we'll always allow GET, HEAD or OPTIONS requests for authenticated users.
        # Public visibility of profiles can be controlled at the queryset level in the view.
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated # Or simply True if profiles are public

        # Write permissions are only allowed to the owner of the account or admin.
        if not request.user.is_authenticated:
            return False
        
        # 'obj' here is the User instance or UserProfile instance.
        # If obj is UserProfile, check obj.user.
        # If obj is User, check obj directly.
        owner = obj.user if hasattr(obj, 'user') and obj.user else obj
        
        return owner == request.user or request.user.is_staff


class IsAccountOwner(BasePermission):
    """
    Allows access only to the owner of the account or admin users for any method.
    Useful for actions that should not even be readable by others unless they are admin.
    """
    message = _("You do not have permission to access or modify this resource.")

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        owner = obj.user if hasattr(obj, 'user') and obj.user else obj
        return owner == request.user or request.user.is_staff


class CanVerifyWhatsApp(BasePermission):
    """
    Allows a user to attempt WhatsApp verification only for their own account.
    """
    message = _("You can only perform WhatsApp verification for your own account.")

    def has_object_permission(self, request, view, obj):
        # obj is expected to be a User instance
        if not request.user.is_authenticated:
            return False
        return obj == request.user or request.user.is_staff


# Example of a more specific permission if needed:
# class CanUpdateOwnSensitiveUserData(BasePermission):
#     """
#     Allows a user to update only their own sensitive User model fields (e.g., password, email).
#     Admin can update anyone's.
#     """
#     message = _("You can only update your own sensitive user data.")
#     def has_object_permission(self, request, view, obj):
#         if not request.user.is_authenticated:
#             return False
#         # obj is a User instance
#         return obj == request.user or request.user.is_staff

# Note: For user registration (create), typically AllowAny is used for the endpoint,
# as the user doesn't exist yet to own anything.
# For listing users (e.g., by an admin), IsAdminUser would be appropriate.
