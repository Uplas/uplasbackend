from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .models import BlogCategory, BlogPost, BlogComment, Author, Tag # Ensure Tag is imported (from projects or own)
# Assuming BasicUserSerializer from users app if needed for direct User FK on BlogPost
# from apps.users.serializers import BasicUserSerializer

User = get_user_model()

# If BasicUserSerializer is needed for direct author field and not available:
class BasicUserSerializerForBlog(serializers.ModelSerializer):
    profile_picture_url = serializers.URLField(source='profile_picture_url', read_only=True, allow_null=True)
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'email', 'profile_picture_url']
        read_only_fields = fields


class BlogCategorySerializer(serializers.ModelSerializer):
    posts_count = serializers.IntegerField(read_only=True, default=0) # Assuming annotated in viewset

    class Meta:
        model = BlogCategory
        fields = ['id', 'name', 'slug', 'description', 'display_order', 'posts_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'slug', 'posts_count', 'created_at', 'updated_at']

class AuthorSerializer(serializers.ModelSerializer): # For the optional Author model
    user_details = BasicUserSerializerForBlog(source='user', read_only=True, allow_null=True) # Nested Uplas user details if linked
    # Use model properties for consistent display name and avatar
    effective_display_name = serializers.CharField(source='get_display_name', read_only=True)
    effective_avatar_url = serializers.URLField(source='get_avatar_url', read_only=True, allow_null=True)

    class Meta:
        model = Author
        fields = [
            'id', 'user', 'user_details', # user is the FK, user_details is nested representation
            'display_name', 'bio', 'avatar_url', # These are fields on Author model itself
            'effective_display_name', 'effective_avatar_url'
        ]
        read_only_fields = ['id', 'user_details', 'effective_display_name', 'effective_avatar_url']
        extra_kwargs = {
            'user': {'write_only': True, 'required': False, 'allow_null': True}, # For linking an Author profile to a User
            'display_name': {'required': True} # Required if creating an Author profile
        }

class BasicTagSerializerForBlog(serializers.ModelSerializer): # For blog posts
    class Meta:
        model = Tag # Assuming Tag is from apps.projects.models.ProjectTag
        fields = ['id', 'name', 'slug']
        read_only_fields = fields


class BlogPostSerializer(serializers.ModelSerializer):
    # Uses model properties for consistent author display
    display_author_name = serializers.CharField(read_only=True)
    display_author_avatar_url = serializers.URLField(read_only=True, allow_null=True)
    
    # If you want to expose the direct FKs for admin/editing and allow selection:
    author_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='author',
        write_only=True, allow_null=False, required=True # An Uplas author is required
    )
    author_profile_override_id = serializers.PrimaryKeyRelatedField(
        queryset=Author.objects.all(), source='author_profile_override',
        write_only=True, allow_null=True, required=False
    )
    
    category = BlogCategorySerializer(read_only=True, allow_null=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=BlogCategory.objects.all(), source='category',
        write_only=True, allow_null=True, required=False
    )
    tags = BasicTagSerializerForBlog(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), source='tags',
        many=True, write_only=True, required=False
    )
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    comment_count = serializers.SerializerMethodField(read_only=True) # Number of approved comments

    class Meta:
        model = BlogPost
        fields = [
            'id', 'title', 'slug',
            'author_id', 'author_profile_override_id', # Writable FKs
            'display_author_name', 'display_author_avatar_url', # Read-only display properties
            'category', 'category_id', 'tags', 'tag_ids',
            'featured_image_url', 'content_html', 'excerpt',
            'status', 'status_display', 'publish_date',
            'meta_description', 'meta_keywords',
            'view_count', 'comment_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'slug', 'display_author_name', 'display_author_avatar_url',
            'category', 'tags', # Nested objects are read-only; use *_id fields for writing
            'status_display',
            'publish_date', # Auto-set based on status
            'view_count', 'comment_count',
            'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'title': {'required': True},
            'content_html': {'required': True},
            'status': {'required': True}, # Explicitly require status on create/update
            'excerpt': {'allow_blank': True, 'required': False},
            'meta_description': {'allow_blank': True, 'required': False},
            'meta_keywords': {'allow_blank': True, 'required': False},
            'featured_image_url': {'allow_blank': True, 'required': False},
        }

    def get_comment_count(self, obj: BlogPost) -> int:
        # If you add a denormalized 'comment_count' field to BlogPost model updated by signals:
        # return obj.comment_count
        # Otherwise, query:
        return obj.comments.filter(is_approved=True).count()

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', None) # 'tags' is source for 'tag_ids'
        post = super().create(validated_data) # author, category, author_profile_override are set via their *_id fields
        if tags_data:
            post.tags.set(tags_data)
        return post

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        instance = super().update(instance, validated_data)
        if tags_data is not None: # Allow clearing tags with empty list
            instance.tags.set(tags_data)
        return instance


class BlogCommentSerializer(serializers.ModelSerializer):
    # Uses model properties for consistent commenter display
    commenter_display_name = serializers.CharField(read_only=True)
    commenter_avatar_url = serializers.URLField(read_only=True, allow_null=True)
    
    # For creating replies
    parent_comment_id = serializers.PrimaryKeyRelatedField(
        queryset=BlogComment.objects.all(), source='parent_comment',
        write_only=True, allow_null=True, required=False
    )
    # For displaying parent (if needed directly, often handled by frontend structure)
    # parent_comment = serializers.PrimaryKeyRelatedField(read_only=True)


    class Meta:
        model = BlogComment
        fields = [
            'id', 'post', # Post is usually from URL context, so write_only or not included for create
            'author', # FK to User, read-only as it's set from request.user
            'author_name', 'author_email', # For guest comments
            'commenter_display_name', 'commenter_avatar_url',
            'content', 'parent_comment_id', #'parent_comment',
            'is_approved', # Read-only for users, writable by admin/moderator
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'author', 'is_approved', # User cannot set/change approval status
            'created_at', 'updated_at',
            'commenter_display_name', 'commenter_avatar_url'
        ]
        extra_kwargs = {
            'post': {'write_only': True, 'required': False}, # Typically set by view from URL
            'author_name': {'required': False, 'allow_blank': False}, # Required if user is not authenticated
            'author_email': {'write_only': True, 'required': False, 'allow_blank': True, 'allow_null': True},
            'content': {'required': True, 'allow_blank': False}
        }

    def validate(self, data):
        request = self.context.get('request')
        user = request.user if request else None
        
        author_fk = data.get('author') # This field is not in serializer for write from user side
        author_name = data.get('author_name')

        if user and user.is_authenticated:
            # If user is authenticated, we ignore author_name/author_email from payload.
            # The view will set 'author' to request.user.
            data.pop('author_name', None)
            data.pop('author_email', None)
        elif not author_name: # Guest comment, name is required
            raise serializers.ValidationError({'author_name': _("Please provide your name to comment.")})
        
        parent_comment = data.get('parent_comment') # This is the resolved parent_comment instance
        post_from_url = self.context.get('post_instance') # View should pass this

        if parent_comment and post_from_url:
            if parent_comment.post != post_from_url:
                raise serializers.ValidationError({'parent_comment_id': _("Reply must be to a comment on the same post.")})
        return data

    def create(self, validated_data):
        # Author is set in the view (perform_create) based on request.user
        # Post is also set in the view from URL context
        return super().create(validated_data)
