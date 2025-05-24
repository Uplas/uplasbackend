from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.contrib.contenttypes.models import ContentType # For generic likes
from rest_framework import serializers

from .models import BlogCategory, BlogPostTag, BlogPost, BlogComment
# Assuming a generic Like model might be in 'community' or a shared app
# from apps.community.models import Like # Example if using community's Like model

User = get_user_model()

# --- Simple User Serializer (for author representation) ---
class SimpleUserSerializer(serializers.ModelSerializer): # Define locally or import from users/core app
    """
    Basic user information for display as author.
    """
    # avatar_url = serializers.URLField(source='userprofile.avatar_url', read_only=True, allow_null=True) # Example
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'email'] # Adjust as per your User model
        read_only_fields = fields


# --- BlogCategory Serializer ---
class BlogCategorySerializer(serializers.ModelSerializer):
    """
    Serializer for BlogCategory model.
    """
    class Meta:
        model = BlogCategory
        fields = ['id', 'name', 'slug', 'description', 'post_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'post_count', 'created_at', 'updated_at']
        extra_kwargs = {
            'slug': {'required': False} # Can be auto-generated from name
        }

    def validate_name(self, value):
        # Example: ensure name is not too short
        if len(value) < 3:
            raise serializers.ValidationError(_("Category name must be at least 3 characters long."))
        return value

    def create(self, validated_data):
        if 'slug' not in validated_data or not validated_data['slug']:
            validated_data['slug'] = self._get_unique_slug(validated_data['name'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'name' in validated_data and ('slug' not in validated_data or not validated_data.get('slug')):
            if validated_data['name'] != instance.name: # Only update slug if name changed and slug not provided
                validated_data['slug'] = self._get_unique_slug(validated_data['name'], instance.pk)
        return super().update(instance, validated_data)

    def _get_unique_slug(self, name, instance_pk=None):
        slug = slugify(name)
        unique_slug = slug
        counter = 1
        qs = BlogCategory.objects.all()
        if instance_pk:
            qs = qs.exclude(pk=instance_pk)
        while qs.filter(slug=unique_slug).exists():
            unique_slug = f'{slug}-{counter}'
            counter += 1
        return unique_slug


# --- BlogPostTag Serializer ---
class BlogPostTagSerializer(serializers.ModelSerializer):
    """
    Serializer for BlogPostTag model.
    """
    class Meta:
        model = BlogPostTag
        fields = ['id', 'name', 'slug', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'slug': {'required': False} # Can be auto-generated from name
        }
    # Similar slug generation logic as BlogCategorySerializer can be added if desired


# --- BlogPost Serializers ---
class BlogPostListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing BlogPosts (summary view).
    """
    author = SimpleUserSerializer(read_only=True)
    category = BlogCategorySerializer(read_only=True)
    tags = BlogPostTagSerializer(many=True, read_only=True)
    # is_liked_by_user = serializers.SerializerMethodField() # If using a generic like system
    status_display = serializers.CharField(source='get_status_display', read_only=True)


    class Meta:
        model = BlogPost
        fields = [
            'id', 'title', 'slug', 'author', 'category', 'tags', 'excerpt',
            'featured_image', 'status', 'status_display', 'published_at',
            'view_count', 'like_count', 'comment_count',
            'created_at', 'updated_at',
            # 'is_liked_by_user'
        ]

    # def get_is_liked_by_user(self, obj):
    #     user = self.context.get('request').user
    #     if user and user.is_authenticated:
    #         # Assuming 'community.Like' model and BlogPost has a GenericRelation 'likes'
    #         # This requires 'community.Like' to be imported and ContentType
    #         try:
    #             content_type = ContentType.objects.get_for_model(obj)
    #             return Like.objects.filter(user=user, content_type=content_type, object_id=obj.id).exists()
    #         except Exception: # Catch potential errors if Like model or ContentType isn't set up
    #             return False
    #     return False


class BlogPostDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed view of a BlogPost.
    """
    author = SimpleUserSerializer(read_only=True)
    category = BlogCategorySerializer(read_only=True)
    tags = BlogPostTagSerializer(many=True, read_only=True)

    # For write operations (create/update)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=BlogCategory.objects.all(), source='category',
        write_only=True, required=False, allow_null=True
    )
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=BlogPostTag.objects.all(), source='tags',
        many=True, write_only=True, required=False
    )
    # is_liked_by_user = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    user_can_edit = serializers.SerializerMethodField()


    class Meta:
        model = BlogPost
        fields = [
            'id', 'title', 'slug', 'author', 'category', 'category_id', 'tags', 'tag_ids',
            'excerpt', 'content_markdown', #'content_html',
            'featured_image', 'status', 'status_display', 'published_at',
            'view_count', 'like_count', 'comment_count',
            'meta_title', 'meta_description',
            'created_at', 'updated_at',
            # 'is_liked_by_user',
            'user_can_edit'
        ]
        read_only_fields = [
            'id', 'author', 'category', 'tags', #'content_html',
            'published_at', 'view_count', 'like_count', 'comment_count',
            'created_at', 'updated_at',
            # 'is_liked_by_user',
            'user_can_edit'
        ]
        extra_kwargs = {
            'slug': {'required': False}, # Auto-generated if not provided
            'content_markdown': {'required': True},
            'excerpt': {'required': False, 'allow_blank': True, 'allow_null': True},
            'featured_image': {'required': False, 'allow_blank': True, 'allow_null': True},
            'meta_title': {'required': False, 'allow_blank': True, 'allow_null': True},
            'meta_description': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    # def get_is_liked_by_user(self, obj):
    #     # Same logic as in BlogPostListSerializer
    #     user = self.context.get('request').user
    #     if user and user.is_authenticated:
    #         try:
    #             content_type = ContentType.objects.get_for_model(obj)
    #             return Like.objects.filter(user=user, content_type=content_type, object_id=obj.id).exists()
    #         except Exception:
    #             return False
    #     return False

    def get_user_can_edit(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return obj.author == user or user.is_staff
        return False

    def validate_title(self, value):
        if len(value) < 10:
            raise serializers.ValidationError(_("Blog post title must be at least 10 characters long."))
        # Add check for title uniqueness if desired, though slug handles URL uniqueness
        return value

    def _handle_tags(self, instance, tags_data):
        if tags_data is not None: # Allow clearing tags by passing empty list
            instance.tags.set(tags_data)

    def create(self, validated_data):
        # Author is set from request context in the view's perform_create
        # Slug is handled by model's save method if not provided
        # Published_at is handled by model's save method based on status
        tags_data = validated_data.pop('tags', None) # From source='tags' for tag_ids
        
        if 'author' not in validated_data and self.context['request'].user.is_authenticated:
             validated_data['author'] = self.context['request'].user

        blog_post = BlogPost.objects.create(**validated_data)
        self._handle_tags(blog_post, tags_data)
        return blog_post

    def update(self, instance, validated_data):
        # Slug and published_at are handled by model's save method
        tags_data = validated_data.pop('tags', None)
        
        # Prevent non-staff from changing author
        if 'author' in validated_data and not self.context['request'].user.is_staff:
            validated_data.pop('author')

        blog_post = super().update(instance, validated_data)
        self._handle_tags(blog_post, tags_data)
        return blog_post


# --- BlogComment Serializers ---
class BlogCommentSerializer(serializers.ModelSerializer):
    """
    Serializer for BlogComment model.
    """
    author = SimpleUserSerializer(read_only=True)
    blog_post_id = serializers.PrimaryKeyRelatedField(
        queryset=BlogPost.objects.filter(status='published'), # Only comment on published posts
        source='blog_post', write_only=True
    )
    parent_comment_id = serializers.PrimaryKeyRelatedField(
        queryset=BlogComment.objects.all(), source='parent_comment',
        write_only=True, required=False, allow_null=True
    )
    # replies = serializers.SerializerMethodField(read_only=True) # For nested display
    # is_liked_by_user = serializers.SerializerMethodField()
    user_can_edit = serializers.SerializerMethodField()
    is_publicly_visible = serializers.BooleanField(read_only=True) # From model property


    class Meta:
        model = BlogComment
        fields = [
            'id', 'blog_post_id', 'author', 'parent_comment_id', 'content',
            'is_approved', 'is_hidden_by_user', 'is_hidden_by_moderator', 'is_publicly_visible',
            'like_count', #'replies',
            'created_at', 'updated_at',
            # 'is_liked_by_user',
            'user_can_edit'
        ]
        read_only_fields = [
            'id', 'author', 'like_count', 'created_at', 'updated_at',
            # 'is_liked_by_user',
            'user_can_edit', 'is_publicly_visible'
        ]
        # Writable by user: content, (blog_post_id, parent_comment_id on create)
        # Writable by moderator: is_approved, is_hidden_by_moderator

    # def get_replies(self, obj):
    #     # Recursive serialization for nested comments (can lead to N+1 if not careful)
    #     # Or limit depth
    #     if obj.replies.exists():
    #         return BlogCommentSerializer(obj.replies.filter(is_publicly_visible=True), many=True, context=self.context).data
    #     return []

    # def get_is_liked_by_user(self, obj):
    #     # Similar logic as for BlogPost
    #     user = self.context.get('request').user
    #     if user and user.is_authenticated:
    #         try:
    #             content_type = ContentType.objects.get_for_model(obj)
    #             return Like.objects.filter(user=user, content_type=content_type, object_id=obj.id).exists()
    #         except Exception:
    #             return False
    #     return False

    def get_user_can_edit(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return obj.author == user or user.is_staff
        return False

    def validate_blog_post_id(self, value): # value is BlogPost instance
        if value.status != 'published':
            raise serializers.ValidationError(_("Comments are only allowed on published blog posts."))
        # Add check for comments_enabled flag on BlogPost if you implement it
        return value

    def validate_parent_comment_id(self, value): # value is BlogComment instance
        # Ensure parent comment belongs to the same blog post as the new comment
        blog_post_id = self.initial_data.get('blog_post_id') # Get the target blog_post_id
        if blog_post_id and value: # If both parent and blog_post are being specified
             # Ensure blog_post_id is a UUID or PK
            try:
                target_blog_post = BlogPost.objects.get(pk=blog_post_id)
                if value.blog_post != target_blog_post:
                    raise serializers.ValidationError(_("Parent comment does not belong to the same blog post."))
            except BlogPost.DoesNotExist:
                 raise serializers.ValidationError(_("Target blog post for comment not found.")) # Should be caught by blog_post_id validation
        return value

    def create(self, validated_data):
        # Author is set from request context in the view
        if 'author' not in validated_data and self.context['request'].user.is_authenticated:
             validated_data['author'] = self.context['request'].user
        # Default is_approved=True, moderators can change it.
        return super().create(validated_data)
