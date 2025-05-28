from rest_framework.permissions import BasePermission, SAFE_METHODS, IsAdminUser
from .models import Course, Module, Topic, Question, Choice, Enrollment, CourseReview

# IsAdminUser is already available from DRF.
# We can use it directly in views for actions restricted to staff/admins.

# Example of a custom permission if instructors are not necessarily staff
# but belong to a specific group or have a flag on their user model.
# class IsInstructorRole(BasePermission):
#     """
#     Allows access only to users with an 'instructor' role.
#     This is a placeholder; actual implementation depends on how roles are defined.
#     """
#     message = "You must have an instructor role to perform this action."
#     def has_permission(self, request, view):
#         if not request.user or not request.user.is_authenticated:
#             return False
#         # Example: Check for a specific group
#         # return request.user.groups.filter(name='Instructors').exists()
#         # Or check a flag on the user model:
#         return getattr(request.user, 'is_instructor_role', False) or request.user.is_staff


class IsInstructorOrReadOnly(BasePermission):
    """
    Allows read access to everyone.
    Allows write access only to the instructor of the course or admin users.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True

        course_instructor = None
        if isinstance(obj, Course): course_instructor = obj.instructor
        elif isinstance(obj, Module): course_instructor = obj.course.instructor
        elif isinstance(obj, Topic): course_instructor = obj.module.course.instructor
        elif isinstance(obj, Question): course_instructor = obj.topic.module.course.instructor
        elif isinstance(obj, Choice): course_instructor = obj.question.topic.module.course.instructor
        
        return course_instructor == request.user


class IsEnrolled(BasePermission):
    message = "You must be enrolled in this course to perform this action."

    def _get_course_from_obj(self, obj):
        if isinstance(obj, Course): return obj
        if hasattr(obj, 'course') and isinstance(obj.course, Course): return obj.course
        if hasattr(obj, 'module') and hasattr(obj.module, 'course'): return obj.module.course
        if hasattr(obj, 'topic') and hasattr(obj.topic, 'module'): return obj.topic.module.course
        if hasattr(obj, 'question') and hasattr(obj.question, 'topic'): return obj.question.topic.module.course
        return None

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        course = getattr(view, 'course_object', None) 
        if not course and hasattr(view, 'kwargs'):
            course_id = view.kwargs.get('course_pk') or view.kwargs.get('course_slug') # Adapt to how course is identified
            if course_id:
                try:
                    lookup_kwarg = 'pk' if isinstance(course_id, (int, uuid.UUID)) else 'slug' # Basic type check
                    course = Course.objects.get(**{lookup_kwarg: course_id})
                except (Course.DoesNotExist, ValueError):
                    return False
        
        if course:
            return Enrollment.objects.filter(user=request.user, course=course).exists() or \
                   (request.user.is_staff or course.instructor == request.user) # Staff/Instructor access
        return True

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated: return False
        course = self._get_course_from_obj(obj)
        if not course: return request.method in SAFE_METHODS 
            
        return Enrollment.objects.filter(user=request.user, course=course).exists() or \
               (request.user.is_staff or course.instructor == request.user) # Staff/Instructor access


class CanViewTopicContent(BasePermission):
    message = "You do not have permission to view this topic's content."

    def has_object_permission(self, request, view, obj):
        if not isinstance(obj, Topic): return False
        course = obj.module.course

        if not course.is_published and not (request.user.is_authenticated and (request.user.is_staff or course.instructor == request.user)):
            return False

        if request.user.is_authenticated:
            if request.user.is_staff or course.instructor == request.user: return True
            if Enrollment.objects.filter(user=request.user, course=course).exists(): return True
        
        return obj.is_previewable or course.is_free
            

class CanPerformEnrolledAction(BasePermission):
    message = "You must be enrolled in the course to perform this action."

    def has_object_permission(self, request, view, obj): # obj is typically Topic or QuizAttempt
        if not request.user.is_authenticated: return False

        course = None
        if isinstance(obj, Topic): course = obj.module.course
        elif hasattr(obj, 'topic') and isinstance(obj.topic, Topic): course = obj.topic.module.course
        else: return False 

        if not course: return False # Should not happen if obj structure is correct
        
        # Instructors/staff can perform these actions regardless of enrollment
        if request.user.is_staff or course.instructor == request.user:
            return True

        if not course.is_published: return False # Regular users cannot interact with unpublished course content
            
        return Enrollment.objects.filter(user=request.user, course=course).exists()


class CanSubmitCourseReview(BasePermission):
    message = "You must be enrolled and not have already reviewed this course to submit a review."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj): # obj is Course for create, CourseReview for update/delete
        if not request.user.is_authenticated: return False
        
        if isinstance(obj, CourseReview): # For update/delete existing review
            return obj.user == request.user or request.user.is_staff
        
        if isinstance(obj, Course): # For creating a new review for this Course object
            if not Enrollment.objects.filter(user=request.user, course=obj).exists():
                self.message = "You must be enrolled in the course to submit a review."
                return False
            if CourseReview.objects.filter(user=request.user, course=obj).exists():
                self.message = "You have already reviewed this course."
                return False
            return True
        return False
