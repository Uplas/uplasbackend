from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .models import (
    CommunityCategory, CommunityGroup, GroupMembership,
    CommunityPost, PostComment, PostReaction
)
# Assuming ProjectTag is the shared tag model
from apps.projects.models import ProjectTag

User = get_user_model()

# Minimal User Serializer for embedding to avoid circular deps and large payloads
class BasicUserSerializerForCommunity(serializers.ModelSerializer):
    # profile_picture_url = serializers.URLField(source='profile.profile_picture_url', read_only=True, allow_null=True) # If User has 'profile' related_name
    profile_picture_url = serializers.URLField(source='profile_picture_url', read_only=True, allow_null=True) # If directly on User model

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'profile_picture_url']
        read_only_fields = fields

class BasicProjectTagSerializer(serializers.ModelSerializer): # For community posts
    class Meta:
        model = ProjectTag
        fields = ['id', 'name', 'slug']
        read_only_fields = fields


class CommunityCategorySerializer(serializers.ModelSerializer):
    posts_count = serializers.IntegerField(read_only=True) # Assuming annotated in viewset

    class Meta:
        model = CommunityCategory
        fields = ['id', 'name', 'slug', 'description', 'icon_url', 'display_order', 'posts_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'slug', 'posts_count', 'created_at', 'updated_at']

class GroupMembershipSerializer(serializers.ModelSerializer):
    user = BasicUserSerializerForCommunity(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = GroupMembership
        fields = ['id', 'user', 'group', 'date_joined', 'role', 'role_display']
        read_only_fields = ['id', 'user', 'group', 'date_joined', 'role_display']
        # 'role' could be writable by group admins through a specific endpoint/action

class CommunityGroupSerializer(serializers.ModelSerializer):
    creator = BasicUserSerializerForCommunity(read_only=True)
    members_count = serializers.IntegerField(read_only=True) # From annotation or SerializerMethodField
    is_member = serializers.BooleanField(read_only=True) # From annotation or SerializerMethodField
    # posts_count = serializers.IntegerField(read_only=True) # Can be annotated

    class Meta:
        model = CommunityGroup
        fields = [
            'id', 'name', 'slug', 'description', 'group_icon_url', 'cover_image_url',
            'creator', 'is_private', 'created_at', 'updated_at',
            'members_count', 'is_member', # 'posts_count'
        ]
        read_only_fields = [
            'id', 'slug', 'creator', 'created_at', 'updated_at',
            'members_count', 'is_member', # 'posts_count'
        ]
    
    # If not using annotations in view for members_count/is_member, use SerializerMethodFields:
    # def get_members_count(self, obj: CommunityGroup) -> int:
    #     return getattr(obj, 'members_annotated_count', obj.members.count())

    # def get_is_member(self, obj: CommunityGroup) -> bool:
    #     user = self.context.get('request').user
    #     if user and user.is_authenticated:
    #         return getattr(obj, 'is_member_annotated', obj.members.filter(id=user.id).exists())
    #     return False


class PostReactionSerializer(serializers.ModelSerializer):
    user = BasicUserSerializerForCommunity(read_only=True)
    reaction_type_display = serializers.CharField(source='get_reaction_type_display', read_only=True)

    class Meta:
        model = PostReaction
        fields = ['id', 'user', 'post', 'comment', 'reaction_type', 'reaction_type_display', 'created_at']
        read_only_fields = ['id', 'user', 'created_at', 'reaction_type_display']
        extra_kwargs = { # For creation
            'post': {'allow_null': True, 'required': False, 'write_only': True},
            'comment': {'allow_null': True, 'required': False, 'write_only': True},
            'reaction_type': {'required': True}
        }

    def validate(self, data):
        post = data.get('post')
        comment = data.get('comment')
        user = self.context['request'].user
        reaction_type = data.get('reaction_type') # This will be validated by ChoiceField on model

        if not post and not comment:
            raise serializers.ValidationError(_("Reaction must be for either a post or a comment."))
        if post and comment:
            raise serializers.ValidationError(_("Reaction cannot be for both a post and a comment simultaneously."))
        
        # Check for existing reaction by this user with this type on this item
        # This logic is more for creation. For updates, the instance would exist.
        # Model's unique_together handles this at DB level.
        # If creating (self.instance is None):
        #    existing_query = {'user': user, 'reaction_type': reaction_type}
        #    if post:
        #        existing_query['post'] = post
        #    else:
        #        existing_query['comment'] = comment
        #    if PostReaction.objects.filter(**existing_query).exists():
        #        raise serializers.ValidationError(_(f"You have already reacted with '{reaction_type}' on this item."))
        return data


class PostCommentSerializer(serializers.ModelSerializer):
    author = BasicUserSerializerForCommunity(read_only=True)
    replies_count = serializers.SerializerMethodField(read_only=True)
    # For full nested replies (can be performance intensive):
    # replies = serializers.SerializerMethodField(read_only=True) 
    
    # Current user's reaction to this comment
    user_reaction_type = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PostComment
        fields = [
            'id', 'post', 'author', 'content_html', 'parent_comment',
            'created_at', 'updated_at', 'reaction_count', 
            'replies_count', #'replies',
            'user_reaction_type'
        ]
        read_only_fields = [
            'id', 'author', 'post', 'created_at', 'updated_at', 
            'reaction_count', 'replies_count', #'replies',
            'user_reaction_type'
        ]
        extra_kwargs = {
            'parent_comment': {'allow_null': True, 'required': False, 'write_only': True},
            'post': {'write_only': True, 'required': False}, # Post usually from URL context
            'content_html': {'required': True}
        }

    def get_replies_count(self, obj: PostComment) -> int:
        # Efficient if replies are prefetched or if it's just a count query
        return obj.replies.count() # Count direct children

    # def get_replies(self, obj: PostComment): # For nested replies
    #     # Only serialize if explicitly requested or within a certain depth
    #     # This can lead to N+1 if not careful or if replies are not prefetched.
    #     # For now, we'll rely on replies_count and fetching replies separately if needed.
    #     # if self.context.get('include_replies', False) and obj.replies.exists():
    #     #     return PostCommentSerializer(obj.replies.all(), many=True, context=self.context).data
    #     return []

    def get_user_reaction_type(self, obj: PostComment) -> str | None:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            # Efficient way: Check for annotated/prefetched reaction
            if hasattr(obj, 'current_user_reaction_on_comment_annotated'): # If view annotated this
                return obj.current_user_reaction_on_comment_annotated
            
            # Fallback query (can be N+1 in lists if not optimized in view)
            reaction = PostReaction.objects.filter(user=user, comment=obj).first()
            return reaction.reaction_type if reaction else None
        return None


class CommunityPostSerializer(serializers.ModelSerializer):
    author = BasicUserSerializerForCommunity(read_only=True)
    category = CommunityCategorySerializer(read_only=True, allow_null=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=CommunityCategory.objects.all(), source='category',
        write_only=True, allow_null=True, required=False
    )
    group = CommunityGroupSerializer(read_only=True, fields=['id', 'name', 'slug', 'group_icon_url'], allow_null=True)
    group_id = serializers.PrimaryKeyRelatedField(
        queryset=CommunityGroup.objects.all(), source='group',
        write_only=True, allow_null=True, required=False
    )
    tags = BasicProjectTagSerializer(many=True, read_only=True) # Use basic tag serializer
    tag_ids = serializers.PrimaryKeyRelatedField( # For writing tags
        queryset=ProjectTag.objects.all(), source='tags',
        many=True, write_only=True, required=False
    )
    
    # Denormalized counts are on the model, so they will be included directly
    # comment_count = serializers.IntegerField(read_only=True)
    # reaction_count = serializers.IntegerField(read_only=True)
    
    # Current user's reaction to this post
    user_reaction_type = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CommunityPost
        fields = [
            'id', 'author', 'title', 'slug', 'content_html',
            'category', 'category_id', 'group', 'group_id', 'tags', 'tag_ids',
            'view_count', 'reaction_count', 'comment_count',
            'is_pinned', 'is_closed', 'last_activity_at',
            'created_at', 'updated_at', 'user_reaction_type'
        ]
        read_only_fields = [
            'id', 'slug', 'author', 'category', 'group', 'tags', # Read-only for nested objects
            'view_count', 'reaction_count', 'comment_count', # These are denormalized and updated by signals/logic
            'last_activity_at', 'created_at', 'updated_at',
            'user_reaction_type'
        ]
        extra_kwargs = {
            'content_html': {'required': True, 'allow_blank': False}
        }

    def get_user_reaction_type(self, obj: CommunityPost) -> str | None:
        user = self.context.get('request').user
        if user and user.is_authenticated:
            # Efficient way: Check for annotated/prefetched reaction
            if hasattr(obj, 'current_user_reaction_on_post_annotated'): # If view annotated this
                return obj.current_user_reaction_on_post_annotated
            
            # Fallback query
            reaction = PostReaction.objects.filter(user=user, post=obj).first()
            return reaction.reaction_type if reaction else None
        return None

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', None) # 'tags' is source for 'tag_ids'
        # Ensure author is set from context, typically done in view's perform_create
        # validated_data['author'] = self.context['request'].user 
        post = CommunityPost.objects.create(**validated_data)
        if tags_data:
            post.tags.set(tags_data)
        return post

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        # Update last_activity_at on significant edit
        # instance.last_activity_at = timezone.now() # Or rely on updated_at for direct edits
        instance = super().update(instance, validated_data)
        if tags_data is not None:
            instance.tags.set(tags_data)
        return instance
