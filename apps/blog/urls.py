from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BlogCategoryViewSet, BlogPostViewSet, BlogCommentViewSet

router = DefaultRouter()
router.register(r'categories', BlogCategoryViewSet, basename='blogcategory')
router.register(r'posts', BlogPostViewSet, basename='blogpost')
router.register(r'comments', BlogCommentViewSet, basename='blogcomment') # For managing individual comments

app_name = 'blog'

urlpatterns = [
    path('', include(router.urls)),
    # Nested routes are handled by @action decorators in BlogPostViewSet:
    # - /api/blog/posts/{slug}/related/
    # - /api/blog/posts/{slug}/comments/ (GET, POST)
]
