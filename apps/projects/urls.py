from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProjectCategoryViewSet, ProjectTagViewSet, ProjectViewSet, UserProjectViewSet
)

router = DefaultRouter()
router.register(r'categories', ProjectCategoryViewSet, basename='projectcategory')
router.register(r'tags', ProjectTagViewSet, basename='projecttag')
router.register(r'projects', ProjectViewSet, basename='project') # For Browse platform projects & suggestions
router.register(r'my-projects', UserProjectViewSet, basename='userproject') # For user's specific project work

app_name = 'projects'

urlpatterns = [
    path('', include(router.urls)),
    # UserProjectViewSet handles:
    #   GET /api/projects/my-projects/  (List user's projects)
    #   POST /api/projects/my-projects/ (To create/start a new UserProject by providing project_id)
    #   GET /api/projects/my-projects/{user_project_id}/ (Retrieve specific user project)
    #   PUT/PATCH /api/projects/my-projects/{user_project_id}/ (Update, e.g. by system)
    #   POST /api/projects/my-projects/start-project/ (Custom action to start)
    #   POST /api/projects/my-projects/{user_project_id}/submit/ (Custom action to submit)
    #   POST /api/projects/my-projects/{user_project_id}/update-assessment/ (Custom action for AI to update)
]
