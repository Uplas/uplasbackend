from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers # For nested routing

from .views import (
    ProjectTagViewSet,
    ProjectViewSet,
    UserProjectViewSet,
    ProjectSubmissionViewSet,
    ProjectAssessmentViewSet
)

app_name = 'projects'

# Main router for top-level resources
router = DefaultRouter()
router.register(r'project-tags', ProjectTagViewSet, basename='project-tag') # e.g., /api/projects/project-tags/
router.register(r'project-definitions', ProjectViewSet, basename='project-definition') # e.g., /api/projects/project-definitions/
router.register(r'user-projects', UserProjectViewSet, basename='user-project') # e.g., /api/projects/user-projects/ (lists user's own or all for admin)
router.register(r'project-assessments', ProjectAssessmentViewSet, basename='project-assessment') # For general listing by admin and AI submission action

# --- Nested Routers ---

# Nested router for Submissions under UserProjects
# URL: /api/projects/user-projects/{user_project_pk}/submissions/
user_projects_router = routers.NestedSimpleRouter(router, r'user-projects', lookup='user_project') # 'user_project' is the lookup kwarg for UserProjectViewSet (pk)
user_projects_router.register(
    r'submissions',
    ProjectSubmissionViewSet,
    basename='userproject-submission' # e.g., userproject-submission-list, userproject-submission-detail
)

# Nested router for Assessment under a specific ProjectSubmission
# URL: /api/projects/user-projects/{user_project_pk}/submissions/{submission_pk}/assessment/
# Since ProjectAssessment has a OneToOne with ProjectSubmission, this will typically point to a single assessment.
# The ProjectAssessmentViewSet is registered here to handle retrieve/update/delete for that specific assessment.
submissions_router = routers.NestedSimpleRouter(user_projects_router, r'submissions', lookup='submission') # 'submission' is the lookup kwarg for ProjectSubmissionViewSet (pk)
submissions_router.register(
    r'assessment', # This will be the endpoint for the single assessment of a submission
    ProjectAssessmentViewSet,
    basename='submission-assessment' # e.g., submission-assessment-detail, submission-assessment-... (custom actions if any)
)


urlpatterns = [
    # Include all router-generated URLs
    path('', include(router.urls)),
    path('', include(user_projects_router.urls)),
    path('', include(submissions_router.urls)),

    # Custom actions on ProjectViewSet (like 'start-project') are automatically routed:
    # e.g., /api/projects/project-definitions/{project_definition_slug}/start-project/

    # Custom actions on ProjectAssessmentViewSet (like 'submit-ai-assessment') are also routed via the top-level registration:
    # e.g., /api/projects/project-assessments/submit-ai-assessment/
]

# --- Example Generated URLs ---
# Top Level:
# /api/projects/project-tags/
# /api/projects/project-tags/{tag_slug}/
# /api/projects/project-definitions/
# /api/projects/project-definitions/{project_definition_slug}/
# /api/projects/project-definitions/{project_definition_slug}/start-project/ (POST)
# /api/projects/user-projects/ (GET for user's own, or all for admin; POST to create a new one - though 'start-project' is preferred)
# /api/projects/user-projects/{user_project_pk}/ (GET, PUT, PATCH, DELETE for owner/admin)
# /api/projects/project-assessments/ (GET list for admin, POST for AI submission action)
# /api/projects/project-assessments/submit-ai-assessment/ (POST)
# /api/projects/project-assessments/{assessment_pk}/ (GET, PUT, PATCH, DELETE for admin/specific viewers)

# Nested:
# /api/projects/user-projects/{user_project_pk}/submissions/ (GET, POST)
# /api/projects/user-projects/{user_project_pk}/submissions/{submission_pk}/ (GET, PUT, PATCH, DELETE)
# /api/projects/user-projects/{user_project_pk}/submissions/{submission_pk}/assessment/ (GET list - usually one item, POST to create if not existing)
# /api/projects/user-projects/{user_project_pk}/submissions/{submission_pk}/assessment/{assessment_pk}/ (GET, PUT, PATCH, DELETE)

