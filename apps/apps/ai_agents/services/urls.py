# uplas-backend/apps/ai_agents/urls.py

from django.urls import path
from .views import (
    NLPTutorView,
    ProjectIdeaGeneratorView,
)

app_name = 'ai_agents'

urlpatterns = [
    # URL for the Personalized NLP Tutor Agent
    path('nlp-tutor/', NLPTutorView.as_view(), name='nlp-tutor'),

    # URL for the Project Idea Generator Agent
    path('project-generator/idea/', ProjectIdeaGeneratorView.as_view(), name='project-generator-idea'),

    # Add other AI agent URLs here as you build them out
    # e.g., path('project-assessor/assess/', ProjectAssessorView.as_view(), name='project-assessor'),
]
