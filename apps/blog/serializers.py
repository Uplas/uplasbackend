from rest_framework import serializers
from .models import BlogCategory, BlogPost, BlogComment, Tag, Author
from apps.users.serializers import UserSerializer # For author details if using User model directly

class BlogCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogCategory
        fields = ['id', 'name', 'slug', 'description', 'display_order']
        read_only_fields = ['id', 'slug']

class AuthorSerializer(serializers.ModelSerializer): # If using separate Author model
    user = UserSerializer(read_only=True, fields=['id', 'username', 'email'])
    class Meta:
        model = Author
        fields = ['id', 'user', 'display_name', 'bio', 'avatar_url']


class BlogPostSerializer(serializers.ModelSerializer):
    # If using direct User FK for author:
    author = UserSerializer(read_only=True, fields=['id', 'username', 'full_name', 'profile_picture_url'])
    # If using Author model FK:
    # author_override = AuthorSerializer(read_only=True, source='author_override_details') # Assuming related name or property
    
    category = BlogCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=BlogCategory.objects.all(), source='category', write_only=True, allow_null=True, required=False
    )
    tags = serializers.StringRelatedField(many=True, read_only=True) # Display tag names
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), source='tags', many=True, write_only=True, required=False
    )
    # comment_count = serializers.IntegerField(source='comments.count', read_only=True) # Better to annotate in view

    class Meta:
        model = BlogPost
        fields = [
            'id', 'title', 'slug', 'author', #'author_override',
            'category', 'category_id', 'tags', 'tag_ids',
            'featured_image_url', 'content_html', 'excerpt',
            'status', 'publish_date', 'meta_description', 'meta_keywords',
            'view_count', #'comment_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'slug', 'author', 'category', 'tags', # read-only for nested objects
            'publish_date', 'view_count', #'comment_count',
            'created_at', 'updated_at'
        ]
        # Admin/Editor only fields for create/update:
        # 'status', 'content_html', 'title', etc.

class BlogCommentSerializer(serializers.ModelSerializer):
    # author = UserSerializer(read_only=True, fields=['id', 'username', 'full_name', 'profile_picture_url']) # If using User FK
    # Use properties for display name and avatar to handle both User and guest commenters
    commenter_display_name = serializers.CharField(read_only=True)
    commenter_avatar_url = serializers.URLField(read_only=True)
    # replies = serializers.SerializerMethodField() # For threaded comments

    class Meta:
        model = BlogComment
        fields = [
            'id', 'post', 'author', 'author_name', 'author_email', # author (FK) for logged-in, author_name/email for guests
            'commenter_display_name', 'commenter_avatar_url',
            'content', 'parent_comment', 'is_approved',
            'created_at', 'updated_at', #'replies'
        ]
        read_only_fields = [
            'id', 'author', 'is_approved', # Approval is admin action
            'created_at', 'updated_at', 'commenter_display_name', 'commenter_avatar_url'
        ]
        extra_kwargs = {
            'post': {'write_only': True}, # Post context from URL
            'parent_comment': {'allow_null': True, 'required': False},
            'author_email': {'write_only': True} # Don't expose email unless necessary
        }

    # def get_replies(self, obj: BlogComment):
    #     if obj.replies.exists():
    #         # Be careful with recursion if directly serializing replies
    #         return BlogCommentSerializer(obj.replies.filter(is_approved=True), many=True, context=self.context).data
    #     return []

    def validate(self, data):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            data['author'] = user # Set authenticated user as author
            data.pop('author_name', None) # Clear guest fields if user is authenticated
            data.pop('author_email', None)
        elif not data.get('author_name'):
            raise serializers.ValidationError({'author_name': "Author name is required for guest comments."})
        return data
