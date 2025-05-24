from rest_framework.permissions import BasePermission, SAFE_METHODS, IsAdminUser
from .models import UserSubscription, PaymentTransaction # Assuming models are in the same app

# IsAdminUser is a built-in DRF permission that can be used directly for admin-only actions.
# IsAuthenticated is also built-in.

class IsSubscriptionOwner(BasePermission):
    """
    Allows access only to the owner of the subscription.
    Admins are implicitly handled if combined with IsAdminUser using OR ( | ) operator in view.
    """
    message = "You do not have permission to access or modify this subscription."

    def has_object_permission(self, request, view, obj):
        # obj is expected to be a UserSubscription instance
        if not isinstance(obj, UserSubscription):
            return False # Or True if the permission should not apply to other objects

        # Allow access if the request.user is the owner of the subscription
        return obj.user == request.user


class IsPaymentTransactionOwner(BasePermission):
    """
    Allows access only to the owner of the payment transaction.
    Admins are implicitly handled if combined with IsAdminUser using OR ( | ) operator in view.
    """
    message = "You do not have permission to access this payment transaction."

    def has_object_permission(self, request, view, obj):
        # obj is expected to be a PaymentTransaction instance
        if not isinstance(obj, PaymentTransaction):
            return False

        # Allow access if the request.user is the owner of the transaction
        return obj.user == request.user


class CanManageSubscription(BasePermission):
    """
    Custom permission to allow users to manage their own subscription
    (e.g., cancel, update payment method - though update PM is usually via Stripe Elements/Portal).
    Also allows admins.
    """
    message = "You do not have permission to manage this subscription."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        if not isinstance(obj, UserSubscription):
            return False # Should only apply to UserSubscription objects

        # Admin users can manage any subscription
        if request.user.is_staff:
            return True
        
        # The user associated with the subscription can manage it
        return obj.user == request.user


class IsAdminOrSubscriptionOwnerReadOnly(BasePermission):
    """
    Allows admin full access.
    Allows subscription owner read-only access.
    Denies access to others.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if not isinstance(obj, UserSubscription):
            return False

        if request.user.is_staff:
            return True # Admin has full access

        # Owner has read-only access
        if obj.user == request.user:
            return request.method in SAFE_METHODS
        
        return False


class IsAdminOrTransactionOwnerReadOnly(BasePermission):
    """
    Allows admin full access.
    Allows transaction owner read-only access.
    Denies access to others.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if not isinstance(obj, PaymentTransaction):
            return False

        if request.user.is_staff:
            return True # Admin has full access

        # Owner has read-only access
        if obj.user == request.user:
            return request.method in SAFE_METHODS
        
        return False

# Note: For SubscriptionPlan, listing might be AllowAny or IsAuthenticated,
# while create/update/delete would strictly be IsAdminUser.
# No specific custom permission might be needed for SubscriptionPlan beyond these.
