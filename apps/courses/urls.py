from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers # For nested routing

from .views import (
    CategoryViewSet,
    CourseViewSet,
    ModuleViewSet,
    TopicViewSet,
    QuestionViewSet,
    CourseReviewViewSet,
    QuizSubmissionView,
    QuizAttemptResultViewSet
)

app_name = 'courses'

# Main router for top-level resources
router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'quiz-attempts', QuizAttemptResultViewSet, basename='quizattempt') # For listing/retrieving own attempts

# Nested router for Modules under Courses
# /api/courses/{course_slug}/modules/
courses_router = routers.NestedSimpleRouter(router, r'courses', lookup='course') # 'course' is the lookup kwarg for CourseViewSet (slug)
courses_router.register(r'modules', ModuleViewSet, basename='course-modules')
# Example: /api/courses/my-awesome-course/modules/

# Nested router for Reviews under Courses
# /api/courses/{course_slug}/reviews/
courses_router.register(r'reviews', CourseReviewViewSet, basename='course-reviews')
# Example: /api/courses/my-awesome-course/reviews/

# Nested router for Topics under Modules (which are under Courses)
# /api/courses/{course_slug}/modules/{module_pk}/topics/
# Note: ModuleViewSet uses default 'pk' lookup
modules_router = routers.NestedSimpleRouter(courses_router, r'modules', lookup='module') # 'module' is the lookup kwarg for ModuleViewSet (pk)
modules_router.register(r'topics', TopicViewSet, basename='module-topics')
# Example: /api/courses/my-awesome-course/modules/123e4567-e89b-12d3-a456-426614174000/topics/

# Nested router for Questions under Topics
# /api/courses/{course_slug}/modules/{module_pk}/topics/{topic_slug}/questions/
# Note: TopicViewSet uses 'slug' lookup
topics_router = routers.NestedSimpleRouter(modules_router, r'topics', lookup='topic') # 'topic' is the lookup kwarg for TopicViewSet (slug)
topics_router.register(r'questions', QuestionViewSet, basename='topic-questions')
# Example: /api/courses/my-awesome-course/modules/123e4567-e89b-12d3-a456-426614174000/topics/my-first-topic/questions/


urlpatterns = [
    # Include all router-generated URLs
    path('', include(router.urls)),
    path('', include(courses_router.urls)),
    path('', include(modules_router.urls)),
    path('', include(topics_router.urls)),

    # Standalone view for quiz submission
    # This could also be a custom action on TopicViewSet if preferred,
    # but a separate endpoint is also clear.
    # POST /api/courses/submit-quiz/ (expects topic_id in request data)
    path('submit-quiz/', QuizSubmissionView.as_view(), name='submit-quiz'),

    # If you had other non-ViewSet views, they would be listed here, for example:
    # path('some-custom-path/', some_custom_view, name='custom-view'),
]

# Example of how URLs will look:
# /api/courses/categories/
# /api/courses/categories/{category_slug}/
# /api/courses/courses/
# /api/courses/courses/{course_slug}/
# /api/courses/courses/{course_slug}/enroll/ (custom action)
# /api/courses/courses/my-courses/ (custom action)
# /api/courses/courses/{course_slug}/modules/
# /api/courses/courses/{course_slug}/modules/{module_pk}/
# /api/courses/courses/{course_slug}/modules/{module_pk}/topics/
# /api/courses/courses/{course_slug}/modules/{module_pk}/topics/{topic_slug}/
# /api/courses/courses/{course_slug}/modules/{module_pk}/topics/{topic_slug}/mark_as_complete/ (custom action)
# /api/courses/courses/{course_slug}/modules/{module_pk}/topics/{topic_slug}/questions/
# /api/courses/courses/{course_slug}/modules/{module_pk}/topics/{topic_slug}/questions/{question_pk}/
# /api/courses/courses/{course_slug}/reviews/
# /api/courses/courses/{course_slug}/reviews/{review_pk}/
# /api/courses/submit-quiz/
# /api/courses/quiz-attempts/
# /api/courses/quiz-attempts/{quizattempt_pk}/
