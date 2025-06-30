import uuid # <-- THIS IS THE CRITICAL FIX
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Exists, OuterRef
from rest_framework import viewsets, status, generics, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

# Django Filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Forum, Thread, Post, Comment, Like, Report, REPORT_STATUS_CHOICES
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
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'author__username': ['exact'],
        'is_pinned': ['exact'],
        'is_closed': ['exact'],
        'forum__slug': ['exact'], 
    }
    search_fields = ['title', 'content', 'author__username', 'forum__name']
    ordering_fields = ['title', 'created_at', 'last_activity_at', 'reply_count', 'view_count', 'like_count']

    def get_serializer_class(self):
        if self.action == 'list':
            return ThreadListSerializer
        return ThreadDetailSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Thread.objects.select_related('author', 'forum')
        
        forum_slug = self.kwargs.get('forum_slug')
        if forum_slug:
            qs = qs.filter(forum__slug=forum_slug)

        if not (user.is_authenticated and user.is_staff):
            qs = qs.filter(is_hidden=False)
        
        return qs.order_by('-is_pinned', '-last_activity_at')

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        elif self.action == 'create':
            return [IsAuthenticated(), CanCreateThreadOrPost()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAuthorOrReadOnly()]
        elif self.action in ['pin_thread', 'close_thread', 'hide_thread']:
            return [IsAuthenticated(), IsModeratorOrAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        forum_slug = self.kwargs.get('forum_slug')
        forum = get_object_or_404(Forum, slug=forum_slug)
        self.check_object_permissions(self.request, forum)
        serializer.save(author=self.request.user, forum=forum)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.view_count += 1
        instance.save(update_fields=['view_count'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
        
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsModeratorOrAdmin])
    def pin_thread(self, request, slug=None):
        thread = self.get_object()
        thread.is_pinned = not thread.is_pinned
        thread.save(update_fields=['is_pinned', 'updated_at'])
        return Response(ThreadDetailSerializer(thread, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsModeratorOrAdmin])
    def close_thread(self, request, slug=None):
        thread = self.get_object()
        thread.is_closed = not thread.is_closed
        thread.save(update_fields=['is_closed', 'updated_at'])
        return Response(ThreadDetailSerializer(thread, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsModeratorOrAdmin])
    def hide_thread(self, request, slug=None):
        thread = self.get_object()
        thread.is_hidden = not thread.is_hidden
        thread.save(update_fields=['is_hidden', 'updated_at'])
        return Response(ThreadDetailSerializer(thread, context={'request': request}).data)

class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = { 'author__username': ['exact'] }
    ordering_fields = ['created_at', 'like_count']

    def get_queryset(self):
        user = self.request.user
        qs = Post.objects.select_related('author', 'thread__forum')
        
        thread_slug_or_pk = self.kwargs.get('thread_slug') or self.kwargs.get('thread_pk')
        if thread_slug_or_pk:
            try:
                uuid.UUID(thread_slug_or_pk)
                qs = qs.filter(thread__pk=thread_slug_or_pk)
            except (ValueError, TypeError):
                qs = qs.filter(thread__slug=thread_slug_or_pk)
        
        if not (user.is_authenticated and user.is_staff):
            qs = qs.filter(is_hidden=False, thread__is_hidden=False)
            
        return qs.order_by('created_at')

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        elif self.action == 'create':
            return [IsAuthenticated(), CanCreateThreadOrPost()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsAuthorOrReadOnly()]
        elif self.action == 'hide_post':
            return [IsAuthenticated(), IsModeratorOrAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        thread_slug = self.kwargs.get('thread_slug')
        thread = get_object_or_404(Thread, slug=thread_slug)
        self.check_object_permissions(self.request, thread)
        serializer.save(author=self.request.user, thread=thread)
        
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsModeratorOrAdmin])
    def hide_post(self, request, pk=None):
        post = self.get_object()
        post.is_hidden = not post.is_hidden # Toggle
        post.save(update_fields=['is_hidden', 'updated_at'])
        return Response(PostSerializer(post, context={'request': request}).data)

class LikeToggleAPIView(generics.GenericAPIView):
    serializer_class = LikeSerializer
    permission_classes = [IsAuthenticated, CanInteractWithContent]

    def _get_target_object(self, request_data):
        content_type_model_str = request_data.get('content_type_model', '').lower()
        object_id_str = request_data.get('object_id')

        if not content_type_model_str or not object_id_str:
            return None, Response({"detail": _("content_type_model and object_id are required.")}, status=status.HTTP_400_BAD_REQUEST)
        
        target_model = None
        try:
            object_id = uuid.UUID(object_id_str)
            app_label = 'community'
            content_type = ContentType.objects.get(app_label=app_label, model=content_type_model_str)
            target_model = content_type.model_class()
            target_object = get_object_or_404(target_model, pk=object_id)
            return target_object, None
        except (ContentType.DoesNotExist, ValueError) as e:
            return None, Response({"detail": _("Invalid content_type_model or object_id.")}, status=status.HTTP_404_NOT_FOUND)
        except Exception: # Catches target_model.DoesNotExist if target_model is None
             if target_model:
                 return None, Response({"detail": _(f"{target_model.__name__} with ID '{object_id_str}' not found.")}, status=status.HTTP_404_NOT_FOUND)
             return None, Response({"detail": _("An unexpected error occurred identifying the target object.")}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, *args, **kwargs): # Like
        target_object, error_response = self._get_target_object(request.data)
        if error_response: return error_response
        self.check_object_permissions(request, target_object)
        content_type = ContentType.objects.get_for_model(target_object)
        _, created = Like.objects.get_or_create(user=request.user, content_type=content_type, object_id=target_object.pk)
        if created:
            return Response({'detail': _('Content liked successfully.'), 'liked': True}, status=status.HTTP_201_CREATED)
        return Response({'detail': _('You have already liked this content.'), 'liked': True}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs): # Unlike
        target_object, error_response = self._get_target_object(request.data)
        if error_response: return error_response
        self.check_object_permissions(request, target_object)
        content_type = ContentType.objects.get_for_model(target_object)
        deleted_count, _ = Like.objects.filter(user=request.user, content_type=content_type, object_id=target_object.pk).delete()
        if deleted_count > 0:
            return Response({'detail': _('Like removed successfully.'), 'liked': False}, status=status.HTTP_200_OK)
        return Response({'detail': _('You have not liked this content or like already removed.'), 'liked': False}, status=status.HTTP_400_BAD_REQUEST)

class ReportCreateAPIView(generics.CreateAPIView):
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated, CanInteractWithContent]
    def perform_create(self, serializer):
        content_type = serializer.validated_data['content_type']
        object_id = serializer.validated_data['object_id']
        ModelClass = content_type.model_class()
        target_object = get_object_or_404(ModelClass, pk=object_id)
        self.check_object_permissions(self.request, target_object)
        serializer.save(reporter=self.request.user)

class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated, CanManageReport]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = { 'status': ['exact', 'in'], 'reporter__username': ['exact'], 'content_type__model': ['exact'], 'resolved_by__username': ['exact'] }
    ordering_fields = ['created_at', 'updated_at', 'status']

    def get_queryset(self):
        if self.request.user.is_staff:
            return Report.objects.all().select_related('reporter', 'resolved_by', 'content_type').prefetch_related('reported_object')
        return Report.objects.none()

    @action(detail=True, methods=['patch'], url_path='update-status')
    def update_status(self, request, pk=None):
        report = self.get_object()
        new_status = request.data.get('status')
        moderator_notes = request.data.get('moderator_notes', report.moderator_notes)
        if not new_status or new_status not in [choice[0] for choice in REPORT_STATUS_CHOICES]:
            return Response({'error': _('Invalid status provided.')}, status=status.HTTP_400_BAD_REQUEST)
        report.status = new_status
        report.moderator_notes = moderator_notes
        report.resolved_by = request.user
        report.save(update_fields=['status', 'moderator_notes', 'resolved_by', 'updated_at'])
        return Response(ReportSerializer(report, context={'request': request}).data)