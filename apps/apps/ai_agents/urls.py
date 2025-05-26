# apps/ai_agents/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter # If using ViewSets for AI client views

from . import views # You will create these views

app_name = 'ai_agents'

# router = DefaultRouter() # Example if you use ViewSets
# router.register(r'tutor', views.AITutorViewSet, basename='ai-tutor')
# router.register(r'tts', views.TextToSpeechViewSet, basename='ai-tts')
# # etc.

urlpatterns = [
    # path('', include(router.urls)), # If using router

    # Example direct paths:
    path('tutor/ask/', views.ask_ai_tutor_view, name='tutor-ask'),
    path('tts/generate/', views.generate_tts_view, name='tts-generate'),
    path('ttv/generate/', views.generate_ttv_view, name='ttv-generate'), # For characters Uncle Trevor, Susan
    path('project/generate-idea/', views.generate_project_idea_view, name='project-generate-idea'),
    path('project/assess/', views.assess_project_view, name='project-assess'),
    # ... other AI-related endpoints this backend will proxy ...
]
