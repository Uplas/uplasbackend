from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.core.views import api_root

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api_root, name='api-root-default'),
    path('api/core/', include('apps.core.urls', namespace='core')),
    path('api/users/', include('apps.users.urls', namespace='users')),
    path('api/courses/', include('apps.courses.urls', namespace='courses')),
    path('api/payments/', include('apps.payments.urls', namespace='payments')),
    path('api/projects/', include('apps.projects.urls', namespace='projects')),
    path('api/community/', include('apps.community.urls', namespace='community')),
    path('api/blog/', include('apps.blog.urls', namespace='blog')),
    path('api/ai/', include('apps.ai_agents.urls', namespace='ai_agents')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
