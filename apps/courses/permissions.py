 from rest_framework import permissions
from .models import UserCourseEnrollment, Topic, Course # Ensure Course is imported

class IsInstructorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow instructors of a course object to edit it.
    Read-only for everyone else.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # For Course objects
        if isinstance(obj, Course):
            return obj.instructor == request.user
        # For Module objects, check instructor of parent course
        if hasattr(obj, 'course') and isinstance(obj.course, Course):
             return obj.course.instructor == request.user
        # For Topic, Quiz, Question, AnswerOption objects, check instructor of grandparent/great-grandparent course
        if hasattr(obj, 'module') and hasattr(obj.module, 'course') and isinstance(obj.module.course, Course): # Topic
             return obj.module.course.instructor == request.user
        if hasattr(obj, 'topic') and hasattr(obj.topic, 'module') and hasattr(obj.topic.module, 'course'): # Quiz
            return obj.topic.module.course.instructor == request.user
        if hasattr(obj, 'quiz') and hasattr(obj.quiz, 'topic') and hasattr(obj.quiz.topic, 'module'): # Question
            return obj.quiz.topic.module.course.instructor == request.user
        if hasattr(obj, 'question') and hasattr(obj.question, 'quiz') and hasattr(obj.question.quiz, 'topic'): # AnswerOption
            return obj.question.quiz.topic.module.course.instructor == request.user
            
        return False # Default to no permission if object structure is unexpected

class IsEnrolled(permissions.BasePermission):
    """
    Checks if the user is enrolled in the course related to the object.
    This permission is typically used for actions like submitting a quiz or marking a topic complete.
    """
    def _get_course_from_object_or_view(self, obj, view):
        """Helper to extract course from object or view kwargs."""
        course = None
        if isinstance(obj, Course):
            course = obj
        elif hasattr(obj, 'course') and isinstance(obj.course, Course): # e.g., Module, Review
            course = obj.course
        elif hasattr(obj, 'module') and hasattr(obj.module, 'course') and isinstance(obj.module.course, Course): # e.g., Topic
            course = obj.module.course
        elif hasattr(obj, 'topic') and hasattr(obj.topic, 'module') and hasattr(obj.topic.module, 'course'): # e.g., Quiz
            course = obj.topic.module.course
        
        if not course: # Try to get from view kwargs if object context isn't direct
            course_slug = view.kwargs.get('course_slug') or view.kwargs.get('slug') # CourseViewSet uses 'slug'
            topic_slug = view.kwargs.get('topic_slug') # TopicViewSet uses 'slug' for topic
            
            if topic_slug: # If topic_slug is present, it has higher precedence for course context
                try:
                    topic_obj = Topic.objects.select_related('module__course').get(slug=topic_slug)
                    course = topic_obj.module.course
                except Topic.DoesNotExist:
                    return None
            elif course_slug:
                 try:
                    course = Course.objects.get(slug=course_slug)
                 except Course.DoesNotExist:
                    return None
        return course

    def has_permission(self, request, view): # For list views or viewset-level checks
        if not request.user or not request.user.is_authenticated:
            return False
        # For viewset actions that don't operate on a specific object yet (e.g. creating an enrollment)
        # this permission might be too broad or need specific handling in the view.
        # Usually, IsEnrolled is best as an object permission.
        # If used as view permission, ensure view provides course context (e.g., from URL).
        
        # Example: If view is for a specific course (e.g. listing modules of a course user must be enrolled in to see)
        course_slug = view.kwargs.get('course_slug') or view.kwargs.get('slug')
        if course_slug:
            try:
                course = Course.objects.get(slug=course_slug)
                return UserCourseEnrollment.objects.filter(user=request.user, course=course).exists()
            except Course.DoesNotExist:
                return False # Course not found, deny permission (or let view 404)
        return True # Default to true if no specific course context at view level, rely on object permission

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        course = self._get_course_from_object_or_view(obj, view)
        if not course:
            return False # Cannot determine course context
            
        return UserCourseEnrollment.objects.filter(user=request.user, course=course).exists()


class IsEnrolledOrPreviewable(permissions.BasePermission):
    """
    Allows access if user is enrolled OR the topic is previewable.
    Primarily for Topic read access.
    """
    def has_object_permission(self, request, view, obj): # obj is expected to be a Topic instance
        if not isinstance(obj, Topic):
            # This permission is specifically for Topics. If applied to something else,
            # it should probably allow or deny based on other criteria.
            # For safety, let's assume it's only for topics.
            return True # Or False, depending on desired default for non-Topic objects

        if obj.is_previewable:
            return True
        
        # If not previewable, user must be authenticated and enrolled
        if not request.user or not request.user.is_authenticated:
            return False
        
        return UserCourseEnrollment.objects.filter(user=request.user, course=obj.module.course).exists()

class CanReviewCourse(permissions.BasePermission):
    """
    Allows a user to create/edit/delete a review if they are enrolled in the course
    and haven't reviewed it yet (for create), or if they are the author of the review (for edit/delete).
    """
    def has_permission(self, request, view): # For POST (create)
        if not request.user or not request.user.is_authenticated:
            return False
        return True # Further checks in has_object_permission or view's perform_create

    def has_object_permission(self, request, view, obj): # obj is a Review instance for PUT/DELETE
        if request.method in permissions.SAFE_METHODS: # GET, HEAD, OPTIONS
            return True
        # For PUT, PATCH, DELETE, user must be the author of the review
        return obj.user == request.user
