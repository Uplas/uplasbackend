# apps/ai_agents/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AIAgentViewSet

router = DefaultRouter()
router.register(r'agents', AIAgentViewSet, basename='agent')

app_name = 'ai_agents'

urlpatterns = [
    path('', include(router.urls)),
]
