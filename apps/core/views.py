from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
from django.utils.translation import gettext_lazy as _

# from rest_framework import viewsets # Example if you add concrete models
# from .models import SystemSetting, FAQ # Example
# from .serializers import SystemSettingSerializer, FAQSerializer # Example

@api_view(['GET'])
def api_root(request, format=None):
    """
    Root endpoint for the UPLAS API.
    Provides a browsable list of available top-level API resources.
    """
    # These names should match the 'basename' used when registering ViewSets in your urls.py files
    # for each app, or the 'name' given to specific path() entries.
    return Response({
        _('users_auth'): reverse('users:user-profile-detail', request=request, format=format), # Example, adjust to your actual user profile URL name
        _('courses'): reverse('courses:course-list', request=request, format=format),
        _('payments_plans'): reverse('payments:subscription-plan-list', request=request, format=format),
        _('projects_definitions'): reverse('projects:project-definition-list', request=request, format=format),
        _('community_forums'): reverse('community:forum-list', request=request, format=format),
        _('blog_posts'): reverse('blog:blog-post-list', request=request, format=format),
        # Add other top-level endpoints here
        # Example for a core model if added:
        # _('faqs'): reverse('core:faq-list', request=request, format=format), # Assuming 'core' namespace and 'faq-list' name
    })

# Example ViewSets if you add concrete models to 'core':
# class SystemSettingViewSet(viewsets.ReadOnlyModelViewSet): # Or ModelViewSet if writable
#     queryset = SystemSetting.objects.all()
#     serializer_class = SystemSettingSerializer
#     permission_classes = [permissions.IsAdminUser] # Example permission

# class FAQViewSet(viewsets.ReadOnlyModelViewSet):
#     queryset = FAQ.objects.filter(is_active=True)
#     serializer_class = FAQSerializer
#     permission_classes = [permissions.AllowAny]
#     filter_backends = [DjangoFilterBackend, SearchFilter]
#     filterset_fields = ['category']
#     search_fields = ['question', 'answer']

