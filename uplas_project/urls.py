# uplas_project/urls.py
"""
URL configuration for uplas_project project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Correctly include the app-level URLs
    path('api/auth/', include('apps.users.urls')),
    path('api/payments/', include('apps.payments.urls')),
    path('api/', include('apps.courses.urls')),
]