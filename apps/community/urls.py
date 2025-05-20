from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CommunityCategoryViewSet, CommunityGroupViewSet, CommunityPostViewSet,
    PostCommentViewSet, TrendingTagsView
)

router = DefaultRouter()
router.register(r'categories', CommunityCategoryViewSet, basename='communitycategory')
router.register(r'groups', CommunityGroupViewSet, basename='communitygroup')
router.register(r'posts', CommunityPostViewSet, basename='communitypost')
router.register(r'comments', PostCommentViewSet, basename='postcomment') # For managing individual comments (edit/delete/react)

app_name = 'community'

urlpatterns = [
    path('', include(router.urls)),
    path('tags/trending/', TrendingTagsView.as_view(), name='trending-tags'),
    # Nested endpoints are handled by @action in ViewSets:
    # - Group posts: /api/community/groups/{group_slug}/posts/
    # - Post comments: /api/community/posts/{post_slug}/comments/
    # - Post reactions: /api/community/posts/{post_slug}/react/
    # - Comment reactions: /api/community/comments/{comment_id}/react/ (via PostCommentViewSet action)
]
