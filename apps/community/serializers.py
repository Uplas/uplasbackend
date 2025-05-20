from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    CommunityCategory, CommunityGroup, GroupMembership,
    CommunityPost, PostComment, PostReaction
)
from apps.users.serializers import UserSerializer # For author, user details
from apps.projects.serializers import ProjectTagSerializer # For tags

User = get_user_model()

class CommunityCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunityCategory
        fields = ['id', 'name', 'slug', 'description', 'icon_url', 'display_order']
        read_only_fields = ['id', 'slug']

class GroupMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True, fields=['id', 'username', 'full_name', 'profile_picture_url'])
    class Meta:
        model = GroupMembership
        fields = ['id', 'user', 'group', 'date_joined', 'role']
        read_only_fields = ['id', 'user', 'group', 'date_joined'] # Role might be updatable by admin

class CommunityGroupSerializer(serializers.ModelSerializer):
    creator = UserSerializer(read_only=True, fields=['id', 'username', 'full_name', 'profile_picture_url'])
    # members_count = serializers.IntegerField(source='members.count', read_only=True) # Handled by annotation in view
    members_count = serializers.SerializerMethodField(read_only=True)
    is_member = serializers.SerializerMethodField(read_only=True) # For current user

    class Meta:
        model = CommunityGroup
        fields = [
            'id', 'name', 'slug', 'description', 'group_icon_url', 'cover_image_url',
            'creator', 'is_private', 'created_at', 'updated_at',
            'members_count', 'is_member'
        ]
        read_only_fields = ['id', 'slug', 'creator', 'created_at', 'updated_at', 'members_count', 'is_member']

    def get_members_count(self, obj: CommunityGroup) -> int:
        # If annotated in queryset, use that, otherwise query
        return getattr(obj, 'members_annotated_count', obj.members.count())

    def get_is_member(self, obj: CommunityGroup) -> bool:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            # If annotated, use that, otherwise query
            return getattr(obj, 'is_member_annotated', obj.members.filter(id=user.id).exists())
        return False


class PostCommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True, fields=['id', 'username', 'full_name', 'profile_picture_url'])
    # replies = serializers.SerializerMethodField(read_only=True) # For nested replies
    # For simplicity, replies can be fetched via a separate endpoint or if depth is limited.
    # Let's make it a simple list for now, or handle nesting in the view if needed for specific depth.
    replies_count = serializers.IntegerField(source='replies.count', read_only=True)
    user_reaction = serializers.SerializerMethodField(read_only=True) # Current user's reaction to this comment

    class Meta:
        model = PostComment
        fields = [
            'id', 'post', 'author', 'content_html', 'parent_comment',
            'created_at', 'updated_at', 'reaction_count', 'replies_count', 'user_reaction'
        ]
        read_only_fields = ['id', 'author', 'post', 'created_at', 'updated_at', 'reaction_count', 'replies_count', 'user_reaction']
        extra_kwargs = {
            'parent_comment': {'allow_null': True, 'required': False},
            'post': {'write_only': True} # Usually provided by context (URL)
        }
    
    def get_user_reaction(self, obj: PostComment) -> str | None:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            try:
                reaction = PostReaction.objects.get(user=user, comment=obj)
                return reaction.reaction_type
            except PostReaction.DoesNotExist:
                return None
        return None

    # def get_replies(self, obj):
    #     # Recursive serialization for replies can be complex and resource-intensive.
    #     # Limit depth or fetch replies via a dedicated endpoint.
    #     # For now, let's assume flat list of comments per post, and replies are linked by parent_comment.
    #     if obj.replies.exists():
    #         # Be careful with recursion depth here if enabling direct nesting
    #         return PostCommentSerializer(obj.replies.all(), many=True, context=self.context).data
    #     return []


class CommunityPostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True, fields=['id', 'username', 'full_name', 'profile_picture_url'])
    category = CommunityCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=CommunityCategory.objects.all(), source='category', write_only=True, allow_null=True, required=False
    )
    group = CommunityGroupSerializer(read_only=True, fields=['id', 'name', 'slug', 'group_icon_url']) # Basic group info
    group_id = serializers.PrimaryKeyRelatedField(
        queryset=CommunityGroup.objects.all(), source='group', write_only=True, allow_null=True, required=False
    )
    tags = ProjectTagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=ProjectTag.objects.all(), source='tags', many=True, write_only=True, required=False
    )
    # comment_count = serializers.IntegerField(source='comments.count', read_only=True) # Denormalized field is better
    # reaction_count = serializers.IntegerField(source='reactions.count', read_only=True) # Denormalized field is better
    user_reaction = serializers.SerializerMethodField(read_only=True) # Current user's reaction to this post

    class Meta:
        model = CommunityPost
        fields = [
            'id', 'author', 'title', 'slug', 'content_html',
            'category', 'category_id', 'group', 'group_id', 'tags', 'tag_ids',
            'view_count', 'reaction_count', 'comment_count',
            'is_pinned', 'is_closed', 'last_activity_at',
            'created_at', 'updated_at', 'user_reaction'
        ]
        read_only_fields = [
            'id', 'slug', 'author', 'category', 'group', 'tags', # Read only for nested objects
            'view_count', 'reaction_count', 'comment_count',
            'last_activity_at', 'created_at', 'updated_at', 'user_reaction'
        ]
        extra_kwargs = {
            'content_html': {'required': True} # Ensure content is provided
        }

    def get_user_reaction(self, obj: CommunityPost) -> str | None:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            try:
                reaction = PostReaction.objects.get(user=user, post=obj)
                return reaction.reaction_type
            except PostReaction.DoesNotExist:
                return None
        return None

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', None)
        post = CommunityPost.objects.create(**validated_data)
        if tags_data:
            post.tags.set(tags_data)
        return post

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        instance = super().update(instance, validated_data)
        if tags_data is not None: # Allow clearing tags with empty list
            instance.tags.set(tags_data)
        return instance


class PostReactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True, fields=['id', 'username'])
    class Meta:
        model = PostReaction
        fields = ['id', 'user', 'post', 'comment', 'reaction_type', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
        extra_kwargs = {
            'post': {'allow_null': True, 'required': False},
            'comment': {'allow_null': True, 'required': False},
        }

    def validate(self, data):
        post = data.get('post')
        comment = data.get('comment')
        if not post and not comment:
            raise serializers.ValidationError("Either 'post' or 'comment' must be provided for a reaction.")
        if post and comment:
            raise serializers.ValidationError("Reaction can only be for a 'post' or a 'comment', not both.")
        
        # Prevent duplicate reactions (handled by model's unique_together, but good to check here too)
        user = self.context['request'].user
        reaction_type = data.get('reaction_type')
        
        query_params = {'user': user, 'reaction_type': reaction_type}
        if post:
            query_params['post'] = post
        else: # comment must exist due to above check
            query_params['comment'] = comment
        
        # If updating, exclude self
        existing_reaction = PostReaction.objects.filter(**query_params)
        if self.instance:
            existing_reaction = existing_reaction.exclude(pk=self.instance.pk)
        
        if existing_reaction.exists():
            raise serializers.ValidationError(f"You have already reacted with '{reaction_type}' on this item.")
            
        return data
