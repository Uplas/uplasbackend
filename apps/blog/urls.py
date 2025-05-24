from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers # For nested routing

from .views import (
    BlogCategoryViewSet,
    BlogPostTagViewSet,
    BlogPostViewSet,
    BlogCommentViewSet
)

app_name = 'blog'

# Main router for top-level blog resources
router = DefaultRouter()
router.register(r'categories', BlogCategoryViewSet, basename='blog-category')
router.register(r'tags', BlogPostTagViewSet, basename='blog-post-tag')
router.register(r'posts', BlogPostViewSet, basename='blog-post')
# BlogCommentViewSet will be nested, but can also be registered at top level for admin/direct access if needed
# router.register(r'all-comments', BlogCommentViewSet, basename='blog-comment-all') # Example if needed

# --- Nested Routers ---

# Comments nested under BlogPosts
# URL: /api/blog/posts/{post_slug}/comments/
# URL: /api/blog/posts/{post_slug}/comments/{comment_pk}/
# BlogPostViewSet uses 'slug' as its lookup_field
posts_router = routers.NestedSimpleRouter(router, r'posts', lookup='post') # 'post' is the lookup kwarg for BlogPostViewSet (slug)
posts_router.register(
    r'comments',
    BlogCommentViewSet,
    basename='blogpost-comment' # e.g., blogpost-comment-list, blogpost-comment-detail
)


urlpatterns = [
    # Include all router-generated URLs
    path('', include(router.urls)),
    path('', include(posts_router.urls)),

    # Custom actions on ViewSets are automatically routed by DefaultRouter.
    # For example, for BlogPostViewSet:
    # /api/blog/posts/{post_slug}/change-status/ (POST)
    #
    # For BlogCommentViewSet (if accessed via its nested route):
    # /api/blog/posts/{post_slug}/comments/{comment_pk}/approve/ (POST)
    # /api/blog/posts/{post_slug}/comments/{comment_pk}/hide/ (POST)
    # /api/blog/posts/{post_slug}/comments/{comment_pk}/toggle-user-hide/ (POST)
]

# --- Example Generated URLs ---
# Top Level:
# /api/blog/categories/
# /api/blog/categories/{category_slug}/
# /api/blog/tags/
# /api/blog/tags/{tag_slug}/
# /api/blog/posts/
# /api/blog/posts/{post_slug}/
# /api/blog/posts/{post_slug}/change-status/ (POST by moderator)

# Nested for Comments:
# /api/blog/posts/{post_slug}/comments/ (GET list, POST create)
# /api/blog/posts/{post_slug}/comments/{comment_pk}/ (GET retrieve, PUT/PATCH update, DELETE)
# /api/blog/posts/{post_slug}/comments/{comment_pk}/approve/ (POST by moderator)
# /api/blog/posts/{post_slug}/comments/{comment_pk}/hide/ (POST by moderator)
# /api/blog/posts/{post_slug}/comments/{comment_pk}/toggle-user-hide/ (POST by comment author)
