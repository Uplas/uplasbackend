from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import BlogCategory, BlogPost, BlogComment, Tag
from .serializers import BlogCategorySerializer, BlogPostSerializer, BlogCommentSerializer
from apps.community.permissions import IsAuthorOrReadOnly # Re-use if applicable or create specific

# Custom permission for blog authors or admin/staff
class IsBlogAuthorOrStaffOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user and request.user.is_staff: # Staff can edit any
            return True
        return obj.author == request.user # Author can edit own post


class BlogCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API for blog categories.
    /api/blog/categories/ 
    """
    queryset = BlogCategory.objects.annotate(posts_count=Count('blog_posts', filter=Q(blog_posts__status='published'))).order_by('display_order')
    serializer_class = BlogCategorySerializer
    permission_classes = [permissions.AllowAny]

class BlogPostViewSet(viewsets.ModelViewSet): # Use ModelViewSet if admin/authors can create/edit via API
    """
    API for blog posts.
    List: /api/blog/posts/ 
    Detail: /api/blog/posts/{slug}/ 
    """
    queryset = BlogPost.objects.filter(status='published', publish_date__lte=timezone.now()).select_related(
        'author', #'author__user_profile', # If using User.profile for avatar
        'category'
    ).prefetch_related('tags', 'comments').annotate(comment_count_annotated=Count('comments', filter=Q(comments__is_approved=True)))
    serializer_class = BlogPostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly] # Read for anyone, write for authenticated (with object permission)
    lookup_field = 'slug'

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsBlogAuthorOrStaffOrReadOnly()]
        # For 'create', ensure user is authenticated and perhaps has specific authoring rights (e.g. staff or designated author role)
        if self.action == 'create':
            return [permissions.IsAdminUser()] # Or a custom permission for authors
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # Allow staff/authors to see their drafts or all drafts
        if user and user.is_authenticated and (user.is_staff or self.action != 'list'): # In detail view, show if owner even if draft
            if self.action == 'retrieve' and self.kwargs.get(self.lookup_field): # For retrieve action
                 # No further status filtering, IsBlogAuthorOrStaffOrReadOnly handles object permission for drafts
                qs_all_status = BlogPost.objects.all().select_related(
                    'author', 'category'
                ).prefetch_related('tags', 'comments').annotate(comment_count_annotated=Count('comments', filter=Q(comments__is_approved=True)))
                return qs_all_status

            # For list view, if staff, show all. If not staff but authenticated, only published.
            if not user.is_staff: # Non-staff users only see published posts in list view
                 qs = qs.filter(status='published', publish_date__lte=timezone.now())
            else: # Staff sees all posts
                 qs_all_status_for_staff = BlogPost.objects.all().select_related(
                    'author', 'category'
                ).prefetch_related('tags', 'comments').annotate(comment_count_annotated=Count('comments', filter=Q(comments__is_approved=True)))
                 qs = qs_all_status_for_staff


        # Filtering for list view
        if self.action == 'list':
            category_slug = self.request.query_params.get('category')
            tag_slug = self.request.query_params.get('tag')
            search_term = self.request.query_params.get('search')

            if category_slug:
                qs = qs.filter(category__slug=category_slug)
            if tag_slug:
                qs = qs.filter(tags__slug=tag_slug)
            if search_term:
                qs = qs.filter(
                    Q(title__icontains=search_term) |
                    Q(content_html__icontains=search_term) |
                    Q(excerpt__icontains=search_term) |
                    Q(tags__name__icontains=search_term)
                ).distinct()
        
        return qs.order_by('-publish_date', '-created_at')


    def perform_create(self, serializer): # If allowing creation via API
        serializer.save(author=self.request.user) # Assign current user as author

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object() # This will apply get_queryset filtering for status unless overridden for retrieve
        
        # Increment view count (simple way, consider rate limiting or unique views for production)
        BlogPost.objects.filter(pk=instance.pk).update(view_count=models.F('view_count') + 1)
        instance.refresh_from_db(fields=['view_count'])
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='related')
    def related_posts(self, request, slug=None): # 
        current_post = self.get_object()
        related = BlogPost.objects.filter(
            status='published',
            publish_date__lte=timezone.now(),
            category=current_post.category # Simple: related by same category
        ).exclude(pk=current_post.pk).annotate(
            comment_count_annotated=Count('comments', filter=Q(comments__is_approved=True))
        ).order_by('?')[:3] # Random 3 related posts
        
        serializer = self.get_serializer(related, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get', 'post'], url_path='comments', serializer_class=BlogCommentSerializer)
    def manage_comments(self, request, slug=None): # 
        post = self.get_object()
        if request.method == 'GET':
            comments = BlogComment.objects.filter(
                post=post, 
                is_approved=True, 
                parent_comment__isnull=True # Top-level comments
            ).select_related(
                'author', #'author__profile'
            ).prefetch_related(
                 Prefetch('replies', queryset=BlogComment.objects.filter(is_approved=True).select_related('author').order_by('created_at'), to_attr='loaded_replies')
            ).order_by('created_at')
            
            page = self.paginate_queryset(comments)
            if page is not None:
                serializer = self.get_serializer(page, many=True, context={'request': request})
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(comments, many=True, context={'request': request})
            return Response(serializer.data)

        elif request.method == 'POST':
            serializer = self.get_serializer(data=request.data, context={'request': request}) # Pass request to context
            if serializer.is_valid():
                serializer.save(post=post) # author is handled by serializer based on auth state
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ViewSet for individual comment management (edit/delete by author/admin)
class BlogCommentViewSet(viewsets.ModelViewSet):
    queryset = BlogComment.objects.all().select_related('author', 'post')
    serializer_class = BlogCommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly] # Read for all, write for author/admin

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            # Custom permission needed: IsCommentAuthorOrStaffOrReadOnly
            return [permissions.IsAuthenticated(), IsBlogAuthorOrStaffOrReadOnly()] # Placeholder, needs IsCommentAuthor
        return super().get_permissions()

    def perform_create(self, serializer): # Comments should be created via nested post endpoint
        raise PermissionDenied("Create comments via the blog post's comment endpoint.")
