from django.urls import path, include
# from rest_framework.routers import DefaultRouter # Example if you add ViewSets
from .views import api_root
# from .views import SystemSettingViewSet, FAQViewSet # Example

app_name = 'core'

# Example if you add ViewSets to the core app:
# router = DefaultRouter()
# router.register(r'system-settings', SystemSettingViewSet, basename='system-setting')
# router.register(r'faqs', FAQViewSet, basename='faq')

urlpatterns = [
    path('', api_root, name='api-root'), # Root of the core app's API paths
    # path('', include(router.urls)), # Example if using a router for core ViewSets
]

