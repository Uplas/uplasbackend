from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Q

from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

# Django Filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import BlogCategory, BlogPostTag, BlogPost, BlogComment
from .serializers import (
    BlogCategorySerializer, BlogPostTagSerializer,
    BlogPostListSerializer, BlogPostDetailSerializer,
    BlogCommentSerializer
)
from .permissions import (
    IsAdminOrReadOnly, IsAuthorOrAdminOrReadOnlyForBlogPost,
    IsCommentAuthorOrAdminOrReadOnly, CanCommentOnPublicPost,
    IsBlogModerator
)

class BlogCategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing blog categories.
    Admins can CRUD, others can read.
    """
    queryset = BlogCategory.objects.all().order_by('name')
    serializer_class = BlogCategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at', 'post_count']


class BlogPostTagViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing blog post tags.
    Admins can CRUD, others can read.
    """
    queryset = BlogPostTag.objects.all().order_by('name')
    serializer_class = BlogPostTagSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']


class BlogPostViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing blog posts.
    - List/Retrieve: Published posts visible to all. Drafts/archived to author/admin.
    - Create: Authenticated users (e.g., staff/authors).
    - Update/Delete: Author or admin.
    """
    queryset = BlogPost.objects.all() # Base queryset, filtered in get_queryset
    permission_classes = [IsAuthorOrAdminOrReadOnlyForBlogPost] # Handles most perms
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'category__slug': ['exact', 'in'],
        'tags__slug': ['exact', 'in'], # Filter by tag slugs
        'status': ['exact', 'in'],
        'author__username': ['exact'],
        'published_at': ['date', 'year', 'month', 'day'],
    }
    search_fields = ['title', 'slug', 'excerpt', 'content_markdown', 'author__username', 'category__name', 'tags__name']
    ordering_fields = ['title', 'published_at', 'created_at', 'updated_at', 'view_count', 'like_count', 'comment_count']

    def get_serializer_class(self):
        if self.action == 'list':
            return BlogPostListSerializer
        return BlogPostDetailSerializer

    def get_queryset(self):
        user = self.request.user
        base_qs = BlogPost.objects.select_related('author__userprofile', 'category').prefetch_related('tags')

        if user.is_authenticated and user.is_staff:
            # Staff/admins can see all posts regardless of status
            return base_qs.all()
        
        if self.action == 'list':
            # Authenticated non-staff users see published posts and their own drafts/archived
            if user.is_authenticated:
                return base_qs.filter(Q(status='published') | Q(author=user)).distinct()
            # Anonymous users see only published posts
            return base_qs.filter(status='published')
        
        # For retrieve, update, delete, IsAuthorOrAdminOrReadOnlyForBlogPost.has_object_permission
        # will handle visibility of draft/archived posts.
        # The initial queryset for these actions can be broader, letting permissions do the work.
        return base_qs.all()


    def perform_create(self, serializer):
        # Author is set by the serializer if not provided and user is authenticated.
        # Or explicitly set it here if serializer doesn't handle it.
        # The BlogPostDetailSerializer's create method already handles setting the author.
        serializer.save() # author=self.request.user is handled in serializer

    def perform_update(self, serializer):
        # Ensure author cannot be changed by non-admins.
        # IsAuthorOrAdminOrReadOnlyForBlogPost handles general edit permission.
        # Serializer's update method also has logic to prevent author change by non-staff.
        serializer.save()

    # Increment view count - typically done on retrieve
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object() # This also runs permission checks
        
        # Increment view count (basic implementation, consider rate limiting or uniqueness for views)
        # Check if it's a legitimate view (e.g., not by a bot or the author themselves repeatedly)
        # For simplicity, we increment on every retrieve for now.
        if instance.status == 'published': # Only count views for published posts
            instance.view_count += 1
            instance.save(update_fields=['view_count', 'updated_at']) # Avoid full save if only view_count changes
            
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsBlogModerator], url_path='change-status', url_name='change-status')
    def change_status(self, request, slug=None):
        """
        Allows a moderator/admin to change the status of a blog post.
        """
        post = self.get_object()
        new_status = request.data.get('status')
        if not new_status or new_status not in [choice[0] for choice in BlogPost.status.field.choices]:
            return Response({'error': _('Invalid status provided.')}, status=status.HTTP_400_BAD_REQUEST)

        post.status = new_status
        # Model's save method handles published_at logic
        post.save(update_fields=['status', 'published_at', 'updated_at'])
        return Response(BlogPostDetailSerializer(post, context={'request': request}).data)


class BlogCommentViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing comments on blog posts.
    - Nested under blog posts (e.g., /api/blog/posts/{post_slug}/comments/).
    - Authenticated users can create comments on published posts.
    - Authors or Admins/Moderators can edit/delete their/any comments.
    - Admins/Moderators can approve/hide comments.
    """
    serializer_class = BlogCommentSerializer
    permission_classes = [IsAuthenticated] # Base, refined per action

    def get_queryset(self):
        user = self.request.user
        post_slug = self.kwargs.get('post_slug_from_url') # Assuming nested URL provides this
        
        qs = BlogComment.objects.select_related('author__userprofile', 'blog_post', 'parent_comment')
        
        if post_slug:
            qs = qs.filter(blog_post__slug=post_slug)
        else: # If accessing comments directly via /api/blog/comments/ (admin use case)
            if not (user.is_authenticated and user.is_staff):
                return BlogComment.objects.none() # Non-admins must access via post

        # Filter for visibility: approved and not hidden by user/moderator
        # Admins/authors see their own even if hidden/unapproved
        if not (user.is_authenticated and user.is_staff):
            # This complex Q object allows authors to see their own non-public comments
            # and everyone to see publicly visible comments.
            publicly_visible_q = Q(is_approved=True, is_hidden_by_user=False, is_hidden_by_moderator=False)
            if user.is_authenticated:
                own_comment_q = Q(author=user)
                qs = qs.filter(publicly_visible_q | own_comment_q).distinct()
            else:
                qs = qs.filter(publicly_visible_q)
        
        return qs.order_by('created_at') # Or '-created_at' for newest first

    def get_permissions(self):
        if self.action == 'create':
            # Permission to create depends on the blog post being commented on
            return [IsAuthenticated(), CanCommentOnPublicPost()]
        elif self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsCommentAuthorOrAdminOrReadOnly()]
        elif self.action in ['approve_comment', 'hide_comment_by_moderator']:
            return [IsAuthenticated(), IsBlogModerator()]
        # For list/retrieve, queryset filtering handles visibility, base IsAuthenticated is fine.
        return super().get_permissions()

    def perform_create(self, serializer):
        post_slug = self.kwargs.get('post_slug_from_url')
        blog_post = get_object_or_404(BlogPost, slug=post_slug)
        
        # CanCommentOnPublicPost permission should be checked against the blog_post object
        self.check_object_permissions(self.request, blog_post) # Pass blog_post to permission

        parent_comment_id = serializer.validated_data.get('parent_comment_id') # This is already validated by serializer
        parent_comment = None
        if parent_comment_id:
            parent_comment = get_object_or_404(BlogComment, pk=parent_comment_id, blog_post=blog_post)

        # Author is set by serializer's create method using context
        serializer.save(blog_post=blog_post, parent_comment=parent_comment)
        # Signal on BlogComment model will update blog_post.comment_count

    def perform_update(self, serializer):
        # IsCommentAuthorOrAdminOrReadOnly handles edit permission.
        # Ensure non-authors/non-admins cannot change blog_post or parent_comment.
        if not self.request.user.is_staff and serializer.instance.author != self.request.user:
            if 'blog_post' in serializer.validated_data or 'parent_comment' in serializer.validated_data:
                 raise serializers.ValidationError(_("You cannot change the associated post or parent comment."))
        serializer.save()

    # --- Moderator Actions for Comments ---
    @action(detail=True, methods=['post'], permission_classes=[IsBlogModerator], url_path='approve', url_name='approve-comment')
    def approve_comment(self, request, pk=None):
        comment = self.get_object()
        comment.is_approved = True
        comment.is_hidden_by_moderator = False # Approving should unhide if mod hid it
        comment.save(update_fields=['is_approved', 'is_hidden_by_moderator', 'updated_at'])
        # Signal on BlogComment save will update BlogPost.comment_count
        return Response(BlogCommentSerializer(comment, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsBlogModerator], url_path='hide', url_name='hide-comment')
    def hide_comment_by_moderator(self, request, pk=None):
        comment = self.get_object()
        comment.is_hidden_by_moderator = not comment.is_hidden_by_moderator # Toggle
        comment.is_approved = False if comment.is_hidden_by_moderator else comment.is_approved # Hiding implies unapproved for public view
        comment.save(update_fields=['is_hidden_by_moderator', 'is_approved', 'updated_at'])
        # Signal on BlogComment save will update BlogPost.comment_count
        return Response(BlogCommentSerializer(comment, context={'request': request}).data)

    # Action for user to hide their own comment (soft delete)
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsCommentAuthorOrAdminOrReadOnly],
            url_path='toggle-user-hide', url_name='toggle-user-hide-comment')
    def toggle_user_hide_comment(self, request, pk=None):
        comment = self.get_object() # Permission checks author
        if comment.author != request.user and not request.user.is_staff: # Double check, though perm should handle
            return Response({'detail': _('Not your comment to hide/unhide.')}, status=status.HTTP_403_FORBIDDEN)
        
        comment.is_hidden_by_user = not comment.is_hidden_by_user
        comment.save(update_fields=['is_hidden_by_user', 'updated_at'])
        # Signal on BlogComment save will update BlogPost.comment_count
        return Response(BlogCommentSerializer(comment, context={'request': request}).data)

