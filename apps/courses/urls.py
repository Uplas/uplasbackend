
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CourseCategoryViewSet, CourseViewSet, TopicViewSet, ReviewViewSet,
    MyCoursesViewSet, QuizSubmissionView
)

router = DefaultRouter()
router.register(r'categories', CourseCategoryViewSet, basename='coursecategory')
router.register(r'courses', CourseViewSet, basename='course') # /api/courses/, /api/courses/{slug}/
router.register(r'topics', TopicViewSet, basename='topic') # /api/topics/{slug}/
router.register(r'my-courses', MyCoursesViewSet, basename='mycourses') # /api/my-courses/

# Nested router for reviews under a course
# /api/courses/{course_slug_from_url}/reviews/
course_reviews_router = DefaultRouter()
course_reviews_router.register(r'reviews', ReviewViewSet, basename='course-review')


app_name = 'courses'

urlpatterns = [
    path('', include(router.urls)),
    
    # Specific endpoint for reviews related to a course
    path('courses/<slug:course_slug_from_url>/', include(course_reviews_router.urls)),

    # Specific endpoint for submitting a quiz for a topic
    path('topics/<slug:topic_slug>/submit-quiz/', QuizSubmissionView.as_view(), name='submit-quiz'),

    # If you want explicit module/topic listing under course like:
    # path('courses/<slug:course_slug>/modules/', CourseModulesListView.as_view(), name='course-modules-list'),
    # path('courses/<slug:course_slug>/modules/<uuid:module_id>/topics/', ModuleTopicsListView.as_view(), name='module-topics-list'),
    # These are currently handled by @action in CourseViewSet and general TopicViewSet
]
