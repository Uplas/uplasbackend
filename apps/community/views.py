from django.db.models import Count, Exists, OuterRef, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction

from rest_framework import viewsets, status, permissions, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError

from .models import (
    CommunityCategory, CommunityGroup, GroupMembership,
    CommunityPost, PostComment, PostReaction
)
from .serializers import (
    CommunityCategorySerializer, CommunityGroupSerializer, GroupMembershipSerializer,
    CommunityPostSerializer, PostCommentSerializer, PostReactionSerializer
)
from .permissions import IsAuthorOrReadOnly, IsGroupAdminOrMemberReadOnly, IsGroupAdminOrCreator # Define these

# Custom Permissions (apps/community/permissions.py)
class IsAuthorOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author == request.user

class IsGroupAdminOrMemberReadOnly(permissions.BasePermission): # For group details
    def has_object_permission(self, request, view, obj: CommunityGroup):
        if request.method in permissions.SAFE_METHODS:
            # Allow read if public, or if private and user is member/creator
            if not obj.is_private or obj.members.filter(id=request.user.id).exists() or obj.creator == request.user:
                return True
            return False # Deny read for private group if not member
        # Write permissions for group details (name, desc) only for creator/admin
        membership = obj.group_memberships.filter(user=request.user).first()
        return obj.creator == request.user or (membership and membership.role in ['admin'])


class IsGroupAdminOrCreator(permissions.BasePermission): # For actions like adding posts to group, managing members
    def has_object_permission(self, request, view, obj: CommunityGroup): # obj is the group
        if not request.user or not request.user.is_authenticated:
            return False
        membership = obj.group_memberships.filter(user=request.user).first()
        return obj.creator == request.user or (membership and membership.role in ['admin', 'moderator'])


class CommunityCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API for community categories.
    /api/community/categories/ 
    """
    queryset = CommunityCategory.objects.annotate(posts_count=Count('posts')).order_by('display_order', 'name')
    serializer_class = CommunityCategorySerializer
    permission_classes = [permissions.AllowAny]

class CommunityGroupViewSet(viewsets.ModelViewSet):
    """
    API for community groups.
    /api/community/groups/ (GET, POST) 
    /api/community/groups/{group_slug}/ (GET, PUT, DELETE) 
    """
    queryset = CommunityGroup.objects.all().select_related('creator')
    serializer_class = CommunityGroupSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly] # Anyone can list/read, auth to create
    lookup_field = 'slug'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        
        # Annotate with members count and if current user is a member for efficiency
        qs = qs.annotate(members_annotated_count=Count('members', distinct=True))
        if user.is_authenticated:
            is_member_subquery = GroupMembership.objects.filter(
                group=OuterRef('pk'),
                user=user
            )
            qs = qs.annotate(is_member_annotated=Exists(is_member_subquery))
        return qs

    def perform_create(self, serializer):
        group = serializer.save(creator=self.request.user)
        # Automatically add creator as an admin member
        GroupMembership.objects.create(user=self.request.user, group=group, role='admin')

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsGroupAdminOrCreator()]
        return super().get_permissions()

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='join')
    def join_group(self, request, slug=None): # 
        group = self.get_object()
        user = request.user
        if group.is_private: # TODO: Implement request-to-join flow for private groups if needed
            return Response({'detail': 'This group is private and requires invitation or approval.'}, status=status.HTTP_403_FORBIDDEN)
        
        membership, created = GroupMembership.objects.get_or_create(user=user, group=group, defaults={'role': 'member'})
        if created:
            return Response({'status': 'Successfully joined group.'}, status=status.HTTP_201_CREATED)
        return Response({'status': 'Already a member of this group.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='leave')
    def leave_group(self, request, slug=None):
        group = self.get_object()
        user = request.user
        membership = GroupMembership.objects.filter(user=user, group=group).first()
        if not membership:
            return Response({'detail': 'Not a member of this group.'}, status=status.HTTP_400_BAD_REQUEST)
        if membership.role == 'admin' and group.creator == user: # Prevent creator/sole admin from leaving easily
             admin_members = group.group_memberships.filter(role='admin').count()
             if admin_members <= 1:
                 return Response({'detail': 'Cannot leave group as the sole admin/creator. Promote another admin first.'}, status=status.HTTP_400_BAD_REQUEST)

        membership.delete()
        return Response({'status': 'Successfully left group.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='posts', serializer_class=CommunityPostSerializer)
    def list_group_posts(self, request, slug=None): # 
        group = self.get_object()
        # Permission check: Can user view this group's posts? (Public or member of private)
        if group.is_private and not group.members.filter(id=request.user.id).exists():
            if not (hasattr(request.user, 'is_staff') and request.user.is_staff): # Allow staff to see for moderation
                return Response({'detail': 'You do not have permission to view posts in this private group.'}, status=status.HTTP_403_FORBIDDEN)

        posts = CommunityPost.objects.filter(group=group).select_related(
            'author', 'category', 'group'
        ).prefetch_related('tags', Prefetch('reactions', queryset=PostReaction.objects.filter(user=request.user), to_attr='current_user_reactions_on_post'))
        
        page = self.paginate_queryset(posts)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(posts, many=True, context={'request': request})
        return Response(serializer.data)

    @list_group_posts.mapping.post # For creating a post within a group
    def create_group_post(self, request, slug=None):
        group = self.get_object()
        # Permission: Must be a member to post (or admin/creator for specific configurations)
        if not group.members.filter(id=request.user.id).exists():
             if not (hasattr(request.user, 'is_staff') and request.user.is_staff):
                return Response({'detail': 'You must be a member of the group to post.'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = CommunityPostSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save(author=request.user, group=group) # Assign author and group
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommunityPostViewSet(viewsets.ModelViewSet):
    """
    API for community posts (general forum, or specific to category/group).
    /api/community/posts/ (GET, POST) 
    /api/community/posts/{post_slug}/ (GET, PUT, DELETE) 
    """
    queryset = CommunityPost.objects.all().select_related(
        'author__profile', 'category', 'group' # Assuming User has a 'profile' for picture_url
    ).prefetch_related(
        'tags',
        Prefetch('reactions', queryset=PostReaction.objects.select_related('user'), to_attr='all_reactions'), # All reactions
        # To get current user's reaction directly on post (if needed by serializer method field)
        # Prefetch('reactions', queryset=PostReaction.objects.filter(user=OuterRef('??request.user??')), to_attr='current_user_reaction_on_post') # This is tricky here
    ).order_by('-is_pinned', '-last_activity_at')
    serializer_class = CommunityPostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = 'slug' # Use slug for post retrieval

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAuthorOrReadOnly()]
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment view count (simple implementation, could be more robust for unique views)
        instance.view_count = models.F('view_count') + 1
        instance.save(update_fields=['view_count'])
        instance.refresh_from_db(fields=['view_count']) # Get the updated value
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        
        # Filtering by category or tag
        category_slug = self.request.query_params.get('category_slug')
        tag_slug = self.request.query_params.get('tag_slug')
        group_slug = self.request.query_params.get('group_slug') # For general listing, can filter by group
        search_term = self.request.query_params.get('search')

        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        if tag_slug:
            qs = qs.filter(tags__slug=tag_slug)
        if group_slug: # Filter posts belonging to a specific group if not using the nested group posts endpoint
            qs = qs.filter(group__slug=group_slug)
        if search_term:
            qs = qs.filter(
                models.Q(title__icontains=search_term) |
                models.Q(content_html__icontains=search_term) |
                models.Q(tags__name__icontains=search_term)
            ).distinct()
            
        # Annotate with current user's reaction (if possible and efficient for list view)
        # This is complex for lists, often handled by SerializerMethodField with a targeted query
        # or by frontend making separate calls for reactions if too slow.
        # For now, user_reaction on serializer will do a lookup.

        return qs


    @action(detail=True, methods=['get', 'post'], url_path='comments', serializer_class=PostCommentSerializer)
    def manage_comments(self, request, slug=None): # 
        post = self.get_object()
        if request.method == 'GET':
            # Get top-level comments for the post
            comments = PostComment.objects.filter(post=post, parent_comment__isnull=True).select_related(
                'author__profile' # Assuming User has profile
            ).prefetch_related(
                Prefetch('replies', queryset=PostComment.objects.select_related('author__profile').order_by('created_at'), to_attr='loaded_replies'), # Load 1st level replies
                Prefetch('reactions', queryset=PostReaction.objects.filter(user=request.user), to_attr='current_user_reactions_on_comment')
            ).order_by('created_at')
            
            page = self.paginate_queryset(comments)
            if page is not None:
                serializer = self.get_serializer(page, many=True, context={'request': request})
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(comments, many=True, context={'request': request})
            return Response(serializer.data)

        elif request.method == 'POST':
            if not request.user.is_authenticated:
                 return Response({'detail': 'Authentication required to comment.'}, status=status.HTTP_401_UNAUTHORIZED)
            if post.is_closed:
                return Response({'detail': 'This post is closed for comments.'}, status=status.HTTP_403_FORBIDDEN)
            
            serializer = self.get_serializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                serializer.save(author=request.user, post=post)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='react', serializer_class=PostReactionSerializer)
    def react_to_post(self, request, slug=None): # 
        post = self.get_object()
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required to react.'}, status=status.HTTP_401_UNAUTHORIZED)

        reaction_type = request.data.get('reaction_type')
        if not reaction_type:
            return Response({'detail': 'reaction_type is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if reaction_type is valid
        valid_reactions = [r[0] for r in PostReaction.REACTION_CHOICES]
        if reaction_type not in valid_reactions:
             return Response({'detail': f'Invalid reaction_type. Valid are: {", ".join(valid_reactions)}'}, status=status.HTTP_400_BAD_REQUEST)


        existing_reaction = PostReaction.objects.filter(user=request.user, post=post).first()
        
        with transaction.atomic():
            if existing_reaction:
                if existing_reaction.reaction_type == reaction_type: # User clicked same reaction again (unlike)
                    existing_reaction.delete()
                    return Response({'status': 'reaction removed'}, status=status.HTTP_204_NO_CONTENT)
                else: # User changed reaction
                    existing_reaction.reaction_type = reaction_type
                    existing_reaction.save()
                    serializer = self.get_serializer(existing_reaction)
                    return Response(serializer.data, status=status.HTTP_200_OK)
            else: # New reaction
                new_reaction = PostReaction.objects.create(user=request.user, post=post, reaction_type=reaction_type)
                serializer = self.get_serializer(new_reaction)
                return Response(serializer.data, status=status.HTTP_201_CREATED)


class PostCommentViewSet(viewsets.ModelViewSet):
    """
    API for individual comments (update, delete, react to comment).
    Typically, comments are created via the nested endpoint under posts.
    This ViewSet is for managing an existing comment.
    """
    queryset = PostComment.objects.all().select_related('author__profile', 'post')
    serializer_class = PostCommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAuthorOrReadOnly()]
        return super().get_permissions()
    
    def perform_create(self, serializer): # Should not be used, create via post's nested endpoint
        raise PermissionDenied("Comments should be created via the post's comment endpoint.")

    @action(detail=True, methods=['post'], url_path='react', serializer_class=PostReactionSerializer)
    def react_to_comment(self, request, pk=None):
        comment = self.get_object()
        # Similar logic to react_to_post
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required to react.'}, status=status.HTTP_401_UNAUTHORIZED)

        reaction_type = request.data.get('reaction_type')
        if not reaction_type:
            return Response({'detail': 'reaction_type is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        valid_reactions = [r[0] for r in PostReaction.REACTION_CHOICES]
        if reaction_type not in valid_reactions:
             return Response({'detail': f'Invalid reaction_type. Valid are: {", ".join(valid_reactions)}'}, status=status.HTTP_400_BAD_REQUEST)

        existing_reaction = PostReaction.objects.filter(user=request.user, comment=comment).first()
        with transaction.atomic():
            if existing_reaction:
                if existing_reaction.reaction_type == reaction_type:
                    existing_reaction.delete()
                    return Response({'status': 'reaction removed'}, status=status.HTTP_204_NO_CONTENT)
                else:
                    existing_reaction.reaction_type = reaction_type
                    existing_reaction.save()
                    serializer = self.get_serializer(existing_reaction) # Use PostReactionSerializer
                    return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                new_reaction = PostReaction.objects.create(user=request.user, comment=comment, reaction_type=reaction_type)
                serializer = self.get_serializer(new_reaction) # Use PostReactionSerializer
                return Response(serializer.data, status=status.HTTP_201_CREATED)

class TrendingTagsView(generics.ListAPIView):
    """
    API for trending community tags.
    /api/community/tags/trending/ 
    """
    # Assuming ProjectTag is the shared tag model
    from apps.projects.models import ProjectTag as CommunityTag
    from apps.projects.serializers import ProjectTagSerializer as CommunityTagSerializer

    serializer_class = CommunityTagSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # Define "trending": e.g., tags used most in recent posts or with most posts overall
        # For simplicity, tags with the most associated community posts
        # Look back N days for recent trending tags.
        since_days = self.request.query_params.get('since_days', 7) # Default to last 7 days
        try:
            since_days = int(since_days)
        except ValueError:
            since_days = 7

        cutoff_date = timezone.now() - timezone.timedelta(days=since_days)
        
        return CommunityTag.objects.filter(
            community_posts_tagged__created_at__gte=cutoff_date
        ).annotate(
            post_count=Count('community_posts_tagged', filter=models.Q(community_posts_tagged__created_at__gte=cutoff_date))
        ).filter(post_count__gt=0).order_by('-post_count', 'name')[:10] # Top 10
