from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Course, Module, Topic, Question, Choice, Enrollment, CourseReview

class IsAdminOrReadOnly(BasePermission):
    """
    Allows full access to admin users, read-only for others.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user and request.user.is_staff

class IsInstructorOrReadOnly(BasePermission):
    """
    Allows read access to everyone.
    Allows write access only to the instructor of the course or admin users.
    This permission is checked at the object level.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in SAFE_METHODS:
            return True

        # Write permissions are only allowed to the instructor of the course or admin.
        if not request.user.is_authenticated:
            return False
        
        if request.user.is_staff: # Admin can do anything
            return True

        course_instructor = None
        if isinstance(obj, Course):
            course_instructor = obj.instructor
        elif isinstance(obj, Module):
            course_instructor = obj.course.instructor
        elif isinstance(obj, Topic):
            course_instructor = obj.module.course.instructor
        elif isinstance(obj, Question):
            course_instructor = obj.topic.module.course.instructor
        elif isinstance(obj, Choice):
            course_instructor = obj.question.topic.module.course.instructor
        
        return course_instructor == request.user


class IsEnrolled(BasePermission):
    """
    Allows access only to users enrolled in the course.
    This permission is typically checked at the object level for course-related objects
    or at the view level if the view context provides a course.
    """
    message = "You must be enrolled in this course to perform this action."

    def _get_course_from_obj(self, obj):
        """Helper to get course from various objects."""
        if isinstance(obj, Course):
            return obj
        if hasattr(obj, 'course') and isinstance(obj.course, Course): # Module, Enrollment, CourseReview, CourseProgress
            return obj.course
        if hasattr(obj, 'module') and hasattr(obj.module, 'course'): # Topic
            return obj.module.course
        if hasattr(obj, 'topic') and hasattr(obj.topic, 'module'): # Question, QuizAttempt
            return obj.topic.module.course
        if hasattr(obj, 'question') and hasattr(obj.question, 'topic'): # Choice
            return obj.question.topic.module.course
        return None

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Try to get course from view (e.g., if it's a nested route or view explicitly sets it)
        course = getattr(view, 'course_object', None) 
        if not course and hasattr(view, 'kwargs'):
            course_id = view.kwargs.get('course_pk') or view.kwargs.get('course_id')
            if course_id:
                try:
                    course = Course.objects.get(pk=course_id)
                except Course.DoesNotExist:
                    return False # Course not found, deny permission
        
        if course:
            return Enrollment.objects.filter(user=request.user, course=course).exists()
        
        # If no course context at view level, rely on object permission or deny if strictly needed here
        # For some views, object permission is sufficient.
        return True # Fallback to object permission if no course context at view level

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        course = self._get_course_from_obj(obj)
        if not course:
            # If we can't determine the course from the object,
            # and it's not a safe method, deny.
            # Safe methods might be allowed if view-level permissions are sufficient.
            return request.method in SAFE_METHODS 
            
        return Enrollment.objects.filter(user=request.user, course=course).exists()


class CanViewTopicContent(BasePermission):
    """
    Allows viewing topic content if:
    - User is enrolled in the course.
    - Topic is previewable and course is published.
    - Course is free and published.
    - User is the instructor or admin.
    """
    message = "You do not have permission to view this topic's content."

    def has_object_permission(self, request, view, obj):
        # Object must be a Topic instance
        if not isinstance(obj, Topic):
            return False # Or True if not a topic, to let other permissions handle it

        course = obj.module.course

        if not course.is_published and not (request.user.is_authenticated and (request.user.is_staff or course.instructor == request.user)):
            return False # Non-instructors/admins cannot see unpublished content

        if request.user.is_authenticated:
            if request.user.is_staff or course.instructor == request.user:
                return True
            if Enrollment.objects.filter(user=request.user, course=course).exists():
                return True
        
        # For both authenticated (but not enrolled/instructor) and unauthenticated users:
        if obj.is_previewable:
            return True
        if course.is_free:
            return True
            
        return False


class CanPerformEnrolledAction(BasePermission):
    """
    Allows actions like marking topics complete or submitting quizzes if enrolled.
    Assumes the object is a Topic or related to a Topic (e.g., QuizAttempt).
    """
    message = "You must be enrolled in the course to perform this action."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        course = None
        if isinstance(obj, Topic):
            course = obj.module.course
        elif hasattr(obj, 'topic') and isinstance(obj.topic, Topic): # e.g. QuizAttempt
             course = obj.topic.module.course
        else:
            # Try to get course from view context if object itself isn't a Topic
            # This might be needed if the permission is on a view directly
            # that doesn't pass a Topic object but has course context.
            # For now, assume obj is Topic or has a direct 'topic' attribute.
            return False 

        if not course or not course.is_published:
             # Allow instructors/admins to interact even if unpublished
            if request.user.is_staff or (course and course.instructor == request.user):
                pass # Allow to proceed to enrollment check or other logic
            else:
                return False

        is_enrolled = Enrollment.objects.filter(user=request.user, course=course).exists()
        
        # Instructors/staff can perform these actions regardless of enrollment (for testing/management)
        if request.user.is_staff or (course and course.instructor == request.user):
            return True
            
        return is_enrolled


class CanSubmitCourseReview(BasePermission):
    """
    Allows a user to submit a review if they are enrolled and haven't reviewed the course yet.
    """
    message = "You must be enrolled and not have already reviewed this course to submit a review."

    def has_permission(self, request, view):
        # This permission is typically used on a create-only view.
        # The course_id should be in the request data or view kwargs.
        if not request.user.is_authenticated:
            return False
        return True # Further checks in has_object_permission or serializer validation

    def has_object_permission(self, request, view, obj):
        # This method is more relevant if updating/deleting own review.
        # For creating, the check is usually done in the view or serializer.
        # If obj is a CourseReview instance (for PUT/DELETE):
        if isinstance(obj, CourseReview):
            return obj.user == request.user or request.user.is_staff
        
        # If obj is a Course instance (for POSTing a new review to this course):
        if isinstance(obj, Course):
            if not request.user.is_authenticated:
                return False
            
            is_enrolled = Enrollment.objects.filter(user=request.user, course=obj).exists()
            if not is_enrolled:
                self.message = "You must be enrolled in the course to submit a review."
                return False
            
            has_reviewed = CourseReview.objects.filter(user=request.user, course=obj).exists()
            if has_reviewed:
                self.message = "You have already reviewed this course."
                return False
            return True
        
        return False # Default deny if object type is not handled
