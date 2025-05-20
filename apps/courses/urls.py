from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CourseCategoryViewSet, CourseViewSet, TopicViewSet, ReviewViewSet,
    MyCoursesViewSet, QuizSubmissionView
)

# Routers provide an easy way of automatically determining the URL conf.
router = DefaultRouter()
router.register(r'categories', CourseCategoryViewSet, basename='coursecategory')
router.register(r'courses', CourseViewSet, basename='course') # Handles /courses/ and /courses/{slug}/
router.register(r'topics', TopicViewSet, basename='topic')   # Handles /topics/ and /topics/{slug}/
router.register(r'my-courses', MyCoursesViewSet, basename='mycourses') # Handles /my-courses/
# router.register(r'reviews', ReviewViewSet, basename='review-detail') # For individual review management if needed outside course nesting

# For nested reviews under a course:
# We'll define this manually as ViewSet nesting with routers can sometimes be tricky for specific actions,
# or we can use a library like drf-nested-routers if we have many nested resources.
# For now, a direct path for course-specific reviews.

app_name = 'courses'

urlpatterns = [
    path('', include(router.urls)),
    
    # Endpoint for reviews related to a specific course
    # GET /api/courses/{course_slug_from_url}/reviews/ - List reviews for this course
    # POST /api/courses/{course_slug_from_url}/reviews/ - Create review for this course
    path('courses/<slug:course_slug_from_url>/reviews/', 
         ReviewViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='course-reviews-list'),
    
    # Endpoint for managing a specific review (if not handled by router.register('reviews',...))
    # GET, PUT, DELETE /api/courses/reviews/{review_pk}/
    # Note: The router for 'reviews' above would create this if not nested under course for list/create.
    # If you want reviews accessible both nested and non-nested:
    # router.register(r'course-reviews', ReviewViewSet, basename='coursereview') # Use a different basename
    # And then for specific review management:
    path('reviews/<uuid:pk>/', 
        ReviewViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='review-detail'),


    # Endpoint for submitting a quiz for a specific topic
    # POST /api/courses/topics/{topic_slug}/submit-quiz/
    path('topics/<slug:topic_slug>/submit-quiz/', QuizSubmissionView.as_view(), name='submit-quiz'),

    # Other custom actions are defined within their ViewSets using @action decorator,
    # e.g., /courses/{course_slug}/enroll/, /topics/{topic_slug}/complete/ etc.
    # The router handles generating URLs for these actions automatically.
]
