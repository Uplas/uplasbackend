from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('apps.users.urls', namespace='users')),
    path('api/courses/', include('apps.courses.urls', namespace='courses')), # Placeholder
    path('api/payments/', include('apps.payments.urls', namespace='payments')), # Placeholder
    path('api/projects/', include('apps.projects.urls', namespace='projects')), # Placeholder
    path('api/community/', include('apps.community.urls', namespace='community')), # Placeholder
    path('api/blog/', include('apps.blog.urls', namespace='blog')), # Placeholder
    
    # API endpoints for AI agents will be added here or under specific apps like courses
    path('api/tts/', include('apps.ai_agents.tts_urls', namespace='tts_agent')), # Example
    path('api/ttv/', include('apps.ai_agents.ttv_urls', namespace='ttv_agent')), # Example
    path('api/ai-tutor/', include('apps.ai_agents.tutor_urls', namespace='ai_tutor')), # Example
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
