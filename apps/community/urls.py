import uuid # Required for UUID path converters if not using slugs everywhere
from django.urls import path, include, register_converter
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers # For nested routing

from .views import (
    ForumViewSet,
    ThreadViewSet,
    PostViewSet,
    # CommentViewSet, # If implemented
    LikeToggleAPIView,
    ReportCreateAPIView,
    ReportViewSet
)

app_name = 'community'

# --- Custom Path Converters (if needed for UUIDs in paths directly) ---
# class UUIDPathConverter:
#     regex = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
#     def to_python(self, value):
#         return uuid.UUID(value)
#     def to_url(self, value):
#         return str(value)
# register_converter(UUIDPathConverter, 'uuid')


# Main router for top-level resources
router = DefaultRouter()
router.register(r'forums', ForumViewSet, basename='forum')
# Registering ThreadViewSet and PostViewSet at top level as well for direct access if needed,
# though primary access might be via nested routes.
# If Thread slugs are globally unique:
router.register(r'threads', ThreadViewSet, basename='thread-global') # For direct access to threads by slug/pk
# If Post PKs are globally unique (less common without thread context):
router.register(r'posts', PostViewSet, basename='post-global') # For direct access to posts by pk

router.register(r'reports', ReportViewSet, basename='report-admin') # For admin management of reports


# --- Nested Routers ---

# Threads nested under Forums
# URL: /api/community/forums/{forum_slug}/threads/
# URL: /api/community/forums/{forum_slug}/threads/{thread_slug}/
forums_router = routers.NestedSimpleRouter(router, r'forums', lookup='forum') # 'forum' is the lookup kwarg for ForumViewSet (slug)
# The 'forum_slug_from_url' kwarg will be available in ThreadViewSet
forums_router.register(r'threads', ThreadViewSet, basename='forum-thread')


# Posts nested under Threads (which are under Forums)
# URL: /api/community/forums/{forum_slug}/threads/{thread_slug_or_pk}/posts/
# URL: /api/community/forums/{forum_slug}/threads/{thread_slug_or_pk}/posts/{post_pk}/
# ThreadViewSet uses 'slug' as lookup_field by default in our example.
# If ThreadViewSet can also be looked up by pk (e.g. for numeric IDs or UUIDs if slugs aren't globally unique), adjust lookup.
# For PostViewSet, the lookup will be its own PK.
# The 'thread_slug_from_url' or 'thread_pk_from_url' kwarg will be available in PostViewSet
threads_router = routers.NestedSimpleRouter(forums_router, r'threads', lookup='thread') # 'thread' is the lookup kwarg for ThreadViewSet (slug or pk)
threads_router.register(r'posts', PostViewSet, basename='thread-post')

# If you implement CommentViewSet nested under Posts:
# posts_router = routers.NestedSimpleRouter(threads_router, r'posts', lookup='post') # 'post' is the lookup for PostViewSet (pk)
# posts_router.register(r'comments', CommentViewSet, basename='post-comment')


urlpatterns = [
    # Include all router-generated URLs
    path('', include(router.urls)),
    path('', include(forums_router.urls)),
    path('', include(threads_router.urls)),
    # path('', include(posts_router.urls)), # If CommentViewSet is added

    # Standalone views for specific actions
    path('like-toggle/', LikeToggleAPIView.as_view(), name='like-toggle'), # POST to like, DELETE to unlike
    path('report-content/', ReportCreateAPIView.as_view(), name='report-content-create'),

    # Custom actions on ViewSets are automatically routed by DefaultRouter.
    # For example, for ThreadViewSet:
    # /api/community/forums/{forum_slug}/threads/{thread_slug}/pin_thread/ (POST)
    # /api/community/threads/{thread_slug}/pin_thread/ (POST) - if using thread-global
    #
    # For ReportViewSet:
    # /api/community/reports/{report_pk}/update-status/ (PATCH)
]

# --- Example Generated URLs ---
# Top Level:
# /api/community/forums/
# /api/community/forums/{forum_slug}/
# /api/community/threads/ (if thread-global registered)
# /api/community/threads/{thread_slug}/ (if thread-global registered)
# /api/community/posts/ (if post-global registered)
# /api/community/posts/{post_pk}/ (if post-global registered)
# /api/community/reports/ (admin listing)
# /api/community/reports/{report_pk}/ (admin detail)
# /api/community/reports/{report_pk}/update-status/ (PATCH by admin)

# Nested:
# /api/community/forums/{forum_slug}/threads/ (GET list, POST create)
# /api/community/forums/{forum_slug}/threads/{thread_slug}/ (GET retrieve, PUT/PATCH update, DELETE)
# /api/community/forums/{forum_slug}/threads/{thread_slug}/pin_thread/ (POST moderator action)
# /api/community/forums/{forum_slug}/threads/{thread_slug}/close_thread/ (POST moderator action)
# /api/community/forums/{forum_slug}/threads/{thread_slug}/hide_thread/ (POST moderator action)

# /api/community/forums/{forum_slug}/threads/{thread_slug_or_pk}/posts/ (GET list, POST create)
# /api/community/forums/{forum_slug}/threads/{thread_slug_or_pk}/posts/{post_pk}/ (GET retrieve, PUT/PATCH update, DELETE)
# /api/community/forums/{forum_slug}/threads/{thread_slug_or_pk}/posts/{post_pk}/hide_post/ (POST moderator action)

# Standalone:
# /api/community/like-toggle/ (POST to like, DELETE to unlike - expects body data)
# /api/community/report-content/ (POST to create a report - expects body data)
