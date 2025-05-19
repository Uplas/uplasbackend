from rest_framework import permissions
from .models import UserCourseEnrollment, Topic, Course

class IsInstructorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow instructors of an object to edit it.
    Assumes the object has an 'instructor' attribute.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        # Write permissions are only allowed to the instructor of the course.
        # This needs to be adapted if modules/topics can have different authors or only course instructor matters.
        if hasattr(obj, 'instructor'): # For Course
            return obj.instructor == request.user
        if hasattr(obj, 'course') and hasattr(obj.course, 'instructor'): # For Module
             return obj.course.instructor == request.user
        if hasattr(obj, 'module') and hasattr(obj.module.course, 'instructor'): # For Topic
             return obj.module.course.instructor == request.user
        return False # Or default to admin/staff only

class IsEnrolled(permissions.BasePermission):
    """
    Checks if the user is enrolled in the course related to the object.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        course = None
        if isinstance(obj, Course):
            course = obj
        elif hasattr(obj, 'course'): # Module, Review
            course = obj.course
        elif hasattr(obj, 'module') and hasattr(obj.module, 'course'): # Topic
            course = obj.module.course
        
        if not course:
            # Fallback for views where obj might not be course-related directly but context is passed
            course_slug_from_url = view.kwargs.get('course_slug_from_url') or view.kwargs.get('course_slug') or view.kwargs.get('slug')
            topic_slug_from_url = view.kwargs.get('topic_slug')
            
            if topic_slug_from_url:
                try:
                    topic_obj = Topic.objects.select_related('module__course').get(slug=topic_slug_from_url)
                    course = topic_obj.module.course
                except Topic.DoesNotExist:
                    return False # Let view handle 404
            elif course_slug_from_url:
                 try:
                    course = Course.objects.get(slug=course_slug_from_url)
                 except Course.DoesNotExist:
                    return False


        if not course: # Could not determine course context
            return False 
            
        return UserCourseEnrollment.objects.filter(user=request.user, course=course).exists()


class IsEnrolledOrPreviewable(permissions.BasePermission):
    """
    Allows access if user is enrolled OR the topic is previewable.
    Primarily for Topic access.
    """
    def has_object_permission(self, request, view, obj: Topic):
        if not isinstance(obj, Topic):
            return True # Not a topic, let other permissions handle

        if obj.is_previewable:
            return True
        
        if not request.user or not request.user.is_authenticated:
            return False # Must be logged in to check enrollment if not previewable
        
        # Check enrollment in the topic's course
        return UserCourseEnrollment.objects.filter(user=request.user, course=obj.module.course).exists()
