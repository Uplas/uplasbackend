from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Exists, OuterRef

from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

# Django Filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Forum, Thread, Post, Comment, Like, Report
from .serializers import (
    ForumListSerializer, ForumDetailSerializer,
    ThreadListSerializer, ThreadDetailSerializer,
    PostSerializer, CommentSerializer,
    LikeSerializer, ReportSerializer
)
from .permissions import (
    IsAdminOrReadOnly, IsAuthorOrReadOnly, CanCreateThreadOrPost,
    IsModeratorOrAdmin, CanInteractWithContent, CanManageReport
)

class ForumViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing forums.
    - Admins can create, update, delete.
    - All users (including anonymous) can list and retrieve.
    """
    queryset = Forum.objects.all().order_by('display_order', 'name')
    permission_classes = [IsAdminOrReadOnly] # ReadOnly for non-admins
    lookup_field = 'slug'
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'display_order', 'created_at', 'thread_count', 'post_count']

    def get_serializer_class(self):
        if self.action == 'list':
            return ForumListSerializer
        return ForumDetailSerializer

    def perform_create(self, serializer):
        # Optionally set created_by if your Forum model has it and you want to track admin creators
        # serializer.save(created_by=self.request.user)
        serializer.save()

class ThreadViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing threads within a forum.
    - Authenticated users can create threads.
    - Authors or Admins/Moderators can edit/delete.
    - Admins/Moderators can pin, close, hide.
    """
    queryset = Thread.objects.all() # Base queryset
    permission_classes = [IsAuthenticated] # Base permission, refined per action
    lookup_field = 'slug' # Or 'pk' if slugs are not globally unique for threads
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'author__username': ['exact'],
        'is_pinned': ['exact'],
        'is_closed': ['exact'],
        'forum__slug': ['exact'], # Filter by parent forum slug
        # 'related_course_id': ['exact'], # If these fields exist
        # 'related_project_id': ['exact'],
    }
    search_fields = ['title', 'content', 'author__username', 'forum__name']
    ordering_fields = ['title', 'created_at', 'last_activity_at', 'reply_count', 'view_count', 'like_count']

    def get_serializer_class(self):
        if self.action == 'list':
            return ThreadListSerializer
        return ThreadDetailSerializer

    def get_queryset(self):
        user = self.request.user
        # Annotate with 'is_liked_by_user' for the current request user
        # This is an alternative to doing it in the serializer, can be more performant for lists.
        # However, SerializerMethodField is often clearer for detail views or if context is complex.
        # For simplicity, we'll rely on the SerializerMethodField for now.

        qs = Thread.objects.select_related('author__userprofile', 'forum') # Optimize
        
        forum_slug = self.kwargs.get('forum_slug_from_url') # Assuming nested URL provides this
        if forum_slug:
            qs = qs.filter(forum__slug=forum_slug)

        # Non-staff/moderators should not see hidden threads in list views
        if not (user.is_authenticated and user.is_staff):
            qs = qs.filter(is_hidden=False)
        
        # Default ordering is by pinned then last activity (from model Meta)
        return qs.order_by('-is_pinned', '-last_activity_at')


    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            # Viewing is generally allowed, but object-level permissions might hide specific content
            return [AllowAny()] # Let object permissions (IsAuthorOrReadOnly for hidden) handle it
        elif self.action == 'create':
            return [IsAuthenticated(), CanCreateThreadOrPost()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAuthorOrReadOnly()]
        elif self.action in ['pin_thread', 'close_thread', 'hide_thread']:
            return [IsAuthenticated(), IsModeratorOrAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        forum_slug = self.kwargs.get('forum_slug_from_url') # From nested URL
        forum = None
        if forum_slug:
            forum = get_object_or_404(Forum, slug=forum_slug)
        elif 'forum_id' in serializer.validated_data: # If forum_id passed directly (less common for nested)
            forum = serializer.validated_data['forum_id'] # This would be a Forum instance if validated
        else: # Fallback if forum_id is expected in direct POST to /threads/
            forum_id_from_data = self.request.data.get('forum') # Assuming 'forum' is the key for forum ID
            if forum_id_from_data:
                 forum = get_object_or_404(Forum, pk=forum_id_from_data)
            else:
                raise serializers.ValidationError({"forum": _("Forum is required to create a thread.")})

        # Check permission to post in this forum (CanCreateThreadOrPost's has_object_permission)
        self.check_object_permissions(self.request, forum)
        serializer.save(author=self.request.user, forum=forum)

    def perform_update(self, serializer):
        # Ensure author and forum are not changed by non-admins during update
        # IsAuthorOrReadOnly handles if user can edit.
        # If admin, they can change anything. If author, they shouldn't change forum.
        if not self.request.user.is_staff and 'forum' in serializer.validated_data:
            if serializer.instance.forum != serializer.validated_data['forum']:
                raise serializers.ValidationError({"forum": _("You cannot change the forum of this thread.")})
        serializer.save()

    # --- Moderator Actions ---
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsModeratorOrAdmin])
    def pin_thread(self, request, slug=None): # Or pk
        thread = self.get_object()
        thread.is_pinned = not thread.is_pinned # Toggle
        thread.save(update_fields=['is_pinned', 'updated_at'])
        return Response(ThreadDetailSerializer(thread, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsModeratorOrAdmin])
    def close_thread(self, request, slug=None): # Or pk
        thread = self.get_object()
        thread.is_closed = not thread.is_closed # Toggle
        thread.save(update_fields=['is_closed', 'updated_at'])
        return Response(ThreadDetailSerializer(thread, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsModeratorOrAdmin])
    def hide_thread(self, request, slug=None): # Or pk
        thread = self.get_object()
        thread.is_hidden = not thread.is_hidden # Toggle
        thread.save(update_fields=['is_hidden', 'updated_at'])
        # If unhiding, might need to re-evaluate forum post counts if they exclude hidden
        return Response(ThreadDetailSerializer(thread, context={'request': request}).data)
    
    # Increment view count - typically done on retrieve
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Basic view count increment, consider rate limiting or more sophisticated tracking
        instance.view_count += 1
        instance.save(update_fields=['view_count'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class PostViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing posts (replies) within a thread.
    """
    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated] # Base, refined per action
    filter_backends = [DjangoFilterBackend, OrderingFilter] # No search on post content usually
    filterset_fields = {
        'author__username': ['exact'],
        # 'thread__slug': ['exact'], # If accessing posts directly, not just nested
    }
    ordering_fields = ['created_at', 'like_count'] # Add 'updated_at' if edits are common

    def get_queryset(self):
        user = self.request.user
        qs = Post.objects.select_related('author__userprofile', 'thread__forum') # Optimize

        thread_slug_or_pk = self.kwargs.get('thread_slug_from_url') or self.kwargs.get('thread_pk_from_url')
        if thread_slug_or_pk:
            # Determine if it's slug or pk (UUID)
            try:
                uuid.UUID(thread_slug_or_pk) # Check if it's a UUID (pk)
                qs = qs.filter(thread__pk=thread_slug_or_pk)
            except ValueError: # Not a UUID, assume slug
                qs = qs.filter(thread__slug=thread_slug_or_pk)
        
        # Non-staff/moderators should not see hidden posts or posts in hidden threads
        if not (user.is_authenticated and user.is_staff):
            qs = qs.filter(is_hidden=False, thread__is_hidden=False)
            
        return qs.order_by('created_at') # Default chronological

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()] # Let object permissions handle hidden content
        elif self.action == 'create':
            return [IsAuthenticated(), CanCreateThreadOrPost()] # Checks thread status
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAuthorOrReadOnly()]
        elif self.action == 'hide_post':
            return [IsAuthenticated(), IsModeratorOrAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        thread_slug_or_pk = self.kwargs.get('thread_slug_from_url') or self.kwargs.get('thread_pk_from_url')
        thread = None
        if thread_slug_or_pk:
             try: # Try PK first if it could be either
                thread = get_object_or_404(Thread, pk=thread_slug_or_pk)
             except (ValueError, Thread.DoesNotExist):
                thread = get_object_or_404(Thread, slug=thread_slug_or_pk)
        elif 'thread_id' in serializer.validated_data:
            thread = serializer.validated_data['thread_id'] # This would be Thread instance
        else:
            thread_id_from_data = self.request.data.get('thread')
            if thread_id_from_data:
                thread = get_object_or_404(Thread, pk=thread_id_from_data)
            else:
                raise serializers.ValidationError({"thread": _("Thread is required to create a post.")})

        # Check permission to post in this thread (CanCreateThreadOrPost's has_object_permission)
        self.check_object_permissions(self.request, thread)
        serializer.save(author=self.request.user, thread=thread)
        # Signal on Post model will update thread's last_activity_at and reply_count

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsModeratorOrAdmin])
    def hide_post(self, request, pk=None):
        post = self.get_object()
        post.is_hidden = not post.is_hidden # Toggle
        post.save(update_fields=['is_hidden', 'updated_at'])
        # Consider recalculating thread reply counts if hidden posts are excluded
        return Response(PostSerializer(post, context={'request': request}).data)


# --- CommentViewSet (If you implement comments on posts) ---
# class CommentViewSet(viewsets.ModelViewSet):
#     serializer_class = CommentSerializer
#     permission_classes = [IsAuthenticated] # Refine per action
#     # ... similar structure to PostViewSet, nested under posts ...
#     pass


# --- Like API View (Not a ViewSet as it's a simple create/delete action) ---
class LikeToggleAPIView(generics.GenericAPIView):
    """
    API endpoint to like or unlike a piece of content (Thread, Post, Comment).
    POST to like, DELETE to unlike.
    Expects 'content_type_model' (e.g., 'thread', 'post') and 'object_id' in request data.
    """
    serializer_class = LikeSerializer # Used for input validation on POST
    permission_classes = [IsAuthenticated, CanInteractWithContent] # CanInteract checks auth and content visibility

    def _get_target_object(self, request_data):
        content_type_model_str = request_data.get('content_type_model', '').lower()
        object_id_str = request_data.get('object_id')

        if not content_type_model_str or not object_id_str:
            return None, Response({"detail": _("content_type_model and object_id are required.")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            object_id = uuid.UUID(object_id_str)
            app_label = 'community' # Assuming models are in 'community'
            content_type = ContentType.objects.get(app_label=app_label, model=content_type_model_str)
            target_model = content_type.model_class()
            target_object = get_object_or_404(target_model, pk=object_id)
            return target_object, None
        except (ContentType.DoesNotExist, ValueError, target_model.DoesNotExist): # Add specific model DoesNotExist if needed
            return None, Response({"detail": _("Invalid content_type_model or object_id.")}, status=status.HTTP_404_NOT_FOUND)


    def post(self, request, *args, **kwargs): # Like
        target_object, error_response = self._get_target_object(request.data)
        if error_response: return error_response

        self.check_object_permissions(request, target_object) # Check CanInteractWithContent

        content_type = ContentType.objects.get_for_model(target_object)
        like, created = Like.objects.get_or_create(
            user=request.user,
            content_type=content_type,
            object_id=target_object.pk
        )

        if created:
            # Signal on Like model will update like_count on target_object
            return Response({'detail': _('Content liked successfully.'), 'liked': True}, status=status.HTTP_201_CREATED)
        return Response({'detail': _('You have already liked this content.'), 'liked': True}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs): # Unlike
        # For DELETE, object_id and content_type_model might be in query_params or request.data
        # Let's assume request.data for consistency with POST for this example
        target_object, error_response = self._get_target_object(request.data)
        if error_response: return error_response
        
        self.check_object_permissions(request, target_object) # Check CanInteractWithContent

        content_type = ContentType.objects.get_for_model(target_object)
        deleted_count, _ = Like.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=target_object.pk
        ).delete()

        if deleted_count > 0:
            # Signal on Like model (post_delete) will update like_count
            return Response({'detail': _('Like removed successfully.'), 'liked': False}, status=status.HTTP_200_OK) # Or 204
        return Response({'detail': _('You have not liked this content or like already removed.'), 'liked': False}, status=status.HTTP_400_BAD_REQUEST)


# --- Report API Views ---
class ReportCreateAPIView(generics.CreateAPIView):
    """
    API endpoint for users to create reports for content.
    """
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated, CanInteractWithContent] # Checks auth and content visibility

    def perform_create(self, serializer):
        # Get target object based on content_type_model and object_id from validated_data
        content_type = serializer.validated_data['content_type'] # Set by serializer.validate()
        object_id = serializer.validated_data['object_id']
        ModelClass = content_type.model_class()
        target_object = get_object_or_404(ModelClass, pk=object_id)
        
        # Check CanInteractWithContent permission against the actual target object
        self.check_object_permissions(self.request, target_object)
        
        serializer.save(reporter=self.request.user)


class ReportViewSet(viewsets.ReadOnlyModelViewSet): # Admins can list/retrieve
    """
    API endpoint for Admins/Moderators to view and manage reports.
    """
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated, CanManageReport] # Admin/Staff only
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = {
        'status': ['exact', 'in'],
        'reporter__username': ['exact'],
        'content_type__model': ['exact'], # e.g., 'thread', 'post'
        'resolved_by__username': ['exact'],
    }
    ordering_fields = ['created_at', 'updated_at', 'status']

    def get_queryset(self):
        # Admins/Staff see all reports
        if self.request.user.is_staff:
            return Report.objects.all().select_related(
                'reporter__userprofile', 'resolved_by__userprofile', 'content_type'
            ).prefetch_related('reported_object') # GenericForeignKey prefetch is tricky
        return Report.objects.none() # Should not be accessible by non-staff

    # Action for admin/moderator to update report status
    @action(detail=True, methods=['patch'], url_path='update-status', url_name='update-report-status')
    def update_status(self, request, pk=None):
        report = self.get_object() # Permission check done by get_object
        
        new_status = request.data.get('status')
        moderator_notes = request.data.get('moderator_notes', report.moderator_notes)

        if not new_status or new_status not in [choice[0] for choice in REPORT_STATUS_CHOICES]:
            return Response({'error': _('Invalid status provided.')}, status=status.HTTP_400_BAD_REQUEST)

        report.status = new_status
        report.moderator_notes = moderator_notes
        report.resolved_by = request.user
        report.save(update_fields=['status', 'moderator_notes', 'resolved_by', 'updated_at'])
        
        # TODO: Optionally, take action based on new_status (e.g., hide content if 'resolved_action_taken')
        # if new_status == 'resolved_action_taken' and report.reported_object:
        #     if hasattr(report.reported_object, 'is_hidden'):
        #         report.reported_object.is_hidden = True
        #         report.reported_object.save(update_fields=['is_hidden'])

        return Response(ReportSerializer(report, context={'request': request}).data)

