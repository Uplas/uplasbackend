from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from rest_framework import serializers

from .models import Forum, Thread, Post, Comment, Like, Report, REPORT_STATUS_CHOICES

User = get_user_model()

# --- Simple User Serializer (for author representation) ---
class SimpleUserSerializer(serializers.ModelSerializer):
    """
    Basic user information for display as author.
    """
    # Add avatar URL if you have it on your UserProfile model
    # avatar_url = serializers.URLField(source='userprofile.avatar_url', read_only=True, allow_null=True)
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'email'] # Customize as needed
        read_only_fields = fields


# --- Forum Serializers ---
class ForumListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing Forums (summary view).
    """
    class Meta:
        model = Forum
        fields = [
            'id', 'name', 'slug', 'description', 'display_order',
            'thread_count', 'post_count', 'is_moderated'
        ]

class ForumDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed view of a Forum.
    Could potentially include a paginated list of recent/pinned threads if desired,
    but usually threads are fetched via a separate endpoint.
    """
    # Example: If you wanted to nest some threads:
    # recent_threads = ThreadListSerializer(many=True, read_only=True, source='get_recent_threads_method_on_model')
    class Meta:
        model = Forum
        fields = [
            'id', 'name', 'slug', 'description', 'display_order',
            'thread_count', 'post_count', 'is_moderated',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'thread_count', 'post_count', 'created_at', 'updated_at']

    def validate_name(self, value):
        # Auto-generate slug if not provided or if name changes
        # This logic is better placed in the model's save() or view's perform_create/update
        # For serializer, we just validate.
        return value


# --- Thread Serializers ---
class ThreadListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing Threads (summary view).
    """
    author = SimpleUserSerializer(read_only=True)
    forum_name = serializers.CharField(source='forum.name', read_only=True)
    forum_slug = serializers.CharField(source='forum.slug', read_only=True)
    is_liked_by_user = serializers.SerializerMethodField()
    user_can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Thread
        fields = [
            'id', 'title', 'slug', 'author', 'forum_name', 'forum_slug', 'forum_id',
            'reply_count', 'view_count', 'like_count',
            'is_pinned', 'is_closed', 'is_hidden',
            'last_activity_at', 'created_at',
            'is_liked_by_user', 'user_can_edit'
        ]

    def get_is_liked_by_user(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            content_type = ContentType.objects.get_for_model(obj)
            return Like.objects.filter(user=user, content_type=content_type, object_id=obj.id).exists()
        return False

    def get_user_can_edit(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return obj.author == user or user.is_staff
        return False

class ThreadDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed view of a Thread.
    Includes initial content. Replies (Posts) are typically fetched via a separate paginated endpoint.
    """
    author = SimpleUserSerializer(read_only=True)
    forum = ForumListSerializer(read_only=True) # Show parent forum details
    is_liked_by_user = serializers.SerializerMethodField()
    user_can_edit = serializers.SerializerMethodField()
    user_can_reply = serializers.SerializerMethodField() # Based on thread status and user auth

    class Meta:
        model = Thread
        fields = [
            'id', 'title', 'slug', 'author', 'forum', 'content', # Initial post content
            'reply_count', 'view_count', 'like_count',
            'is_pinned', 'is_closed', 'is_hidden',
            'last_activity_at', 'created_at', 'updated_at',
            'is_liked_by_user', 'user_can_edit', 'user_can_reply'
            # 'related_course_id', 'related_project_id' # If these fields are added to model
        ]
        read_only_fields = [
            'id', 'author', 'forum', 'reply_count', 'view_count', 'like_count',
            'last_activity_at', 'created_at', 'updated_at',
            'is_liked_by_user', 'user_can_edit', 'user_can_reply'
        ]
        # Fields for creation/update by user: title, content, (forum_id on create)
        # Fields for moderation: is_pinned, is_closed, is_hidden (by staff)

    def get_is_liked_by_user(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            content_type = ContentType.objects.get_for_model(obj)
            return Like.objects.filter(user=user, content_type=content_type, object_id=obj.id).exists()
        return False

    def get_user_can_edit(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return obj.author == user or user.is_staff
        return False

    def get_user_can_reply(self, obj):
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            return False
        if obj.is_closed:
            return False
        if obj.is_hidden and not user.is_staff:
            return False
        return True

    def validate_title(self, value):
        if len(value) < 5: # Example validation
            raise serializers.ValidationError(_("Title must be at least 5 characters long."))
        return value

    def create(self, validated_data):
        # Author is set from request context in the view
        # Slug can be auto-generated if not provided
        if 'slug' not in validated_data or not validated_data['slug']:
            base_slug = slugify(validated_data['title'])
            slug = base_slug
            counter = 1
            while Thread.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            validated_data['slug'] = slug
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Slug might need to be regenerated if title changes and slug is not provided
        if 'title' in validated_data and 'slug' not in validated_data:
            if validated_data['title'] != instance.title:
                base_slug = slugify(validated_data['title'])
                slug = base_slug
                counter = 1
                # Ensure uniqueness if auto-generating and title changed
                while Thread.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                validated_data['slug'] = slug
        return super().update(instance, validated_data)


# --- Post (Reply) Serializers ---
class PostSerializer(serializers.ModelSerializer):
    """
    Serializer for Posts (replies within a thread).
    """
    author = SimpleUserSerializer(read_only=True)
    thread_title = serializers.CharField(source='thread.title', read_only=True)
    thread_id = serializers.PrimaryKeyRelatedField(
        queryset=Thread.objects.all(), source='thread', write_only=True
    )
    is_liked_by_user = serializers.SerializerMethodField()
    user_can_edit = serializers.SerializerMethodField()
    # comments = CommentSerializer(many=True, read_only=True) # If nesting comments directly

    class Meta:
        model = Post
        fields = [
            'id', 'thread_id', 'thread_title', 'author', 'content',
            'like_count', 'is_hidden', #'comment_count',
            'created_at', 'updated_at',
            'is_liked_by_user', 'user_can_edit'
        ]
        read_only_fields = [
            'id', 'author', 'thread_title', 'like_count', #'comment_count',
            'created_at', 'updated_at',
            'is_liked_by_user', 'user_can_edit'
        ]
        # Fields for creation/update: content, (thread_id on create)
        # Field for moderation: is_hidden

    def get_is_liked_by_user(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            content_type = ContentType.objects.get_for_model(obj)
            return Like.objects.filter(user=user, content_type=content_type, object_id=obj.id).exists()
        return False

    def get_user_can_edit(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return obj.author == user or user.is_staff
        return False

    def validate_thread_id(self, value): # value is Thread instance
        if value.is_closed:
            raise serializers.ValidationError(_("Cannot post to a closed thread."))
        if value.is_hidden and not (self.context['request'].user and self.context['request'].user.is_staff):
            raise serializers.ValidationError(_("Cannot post to a hidden thread."))
        return value

    def validate_content(self, value):
        if len(value) < 2: # Example validation
            raise serializers.ValidationError(_("Post content is too short."))
        return value


# --- Comment Serializer (if used) ---
class CommentSerializer(serializers.ModelSerializer):
    author = SimpleUserSerializer(read_only=True)
    post_id = serializers.PrimaryKeyRelatedField(
        queryset=Post.objects.all(), source='post', write_only=True
    )
    is_liked_by_user = serializers.SerializerMethodField()
    user_can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id', 'post_id', 'author', 'content', 'like_count',
            'is_hidden', 'created_at', 'updated_at',
            'is_liked_by_user', 'user_can_edit'
        ]
        read_only_fields = [
            'id', 'author', 'like_count', 'created_at', 'updated_at',
            'is_liked_by_user', 'user_can_edit'
        ]

    def get_is_liked_by_user(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            content_type = ContentType.objects.get_for_model(obj)
            return Like.objects.filter(user=user, content_type=content_type, object_id=obj.id).exists()
        return False

    def get_user_can_edit(self, obj):
        user = self.context.get('request').user
        if user and user.is_authenticated:
            return obj.author == user or user.is_staff
        return False

    def validate_post_id(self, value): # value is Post instance
        if value.is_hidden and not (self.context['request'].user and self.context['request'].user.is_staff):
            raise serializers.ValidationError(_("Cannot comment on a hidden post."))
        if value.thread.is_closed:
            raise serializers.ValidationError(_("Cannot comment on a post in a closed thread."))
        if value.thread.is_hidden and not (self.context['request'].user and self.context['request'].user.is_staff):
             raise serializers.ValidationError(_("Cannot comment on a post in a hidden thread."))
        return value


# --- Like Serializer ---
class LikeSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/deleting Likes.
    Uses content_type and object_id to identify the liked object.
    """
    user = SimpleUserSerializer(read_only=True) # User is set from request context
    content_type_model = serializers.CharField(write_only=True, help_text=_("Model name of the liked object (e.g., 'thread', 'post', 'comment')."))
    object_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Like
        fields = ['id', 'user', 'content_type_model', 'object_id', 'created_at']
        read_only_fields = ['id', 'user', 'created_at'] # content_type is derived

    def validate_content_type_model(self, value):
        value = value.lower()
        allowed_models = ['thread', 'post', 'comment'] # Extend as needed
        if value not in allowed_models:
            raise serializers.ValidationError(_(f"Liking is not supported for model '{value}'. Allowed: {', '.join(allowed_models)}"))
        return value

    def validate(self, data):
        content_type_model = data.get('content_type_model')
        object_id = data.get('object_id')
        user = self.context['request'].user

        try:
            # Map model name string to ContentType object
            app_label = 'community' # Assuming all likeable models are in 'community' app
            content_type = ContentType.objects.get(app_label=app_label, model=content_type_model)
        except ContentType.DoesNotExist:
            raise serializers.ValidationError({'content_type_model': _(f"Invalid model type '{content_type_model}'.")})

        # Check if the object exists
        ModelClass = content_type.model_class()
        if not ModelClass.objects.filter(pk=object_id).exists():
            raise serializers.ValidationError({'object_id': _(f"{ModelClass.__name__} with ID '{object_id}' not found.")})
        
        # Check for hidden content (using CanInteractWithContent logic as a guide)
        liked_object = ModelClass.objects.get(pk=object_id)
        if hasattr(liked_object, 'is_hidden') and liked_object.is_hidden and not user.is_staff:
            raise serializers.ValidationError(_("Cannot like hidden content."))
        
        parent_thread = None
        if isinstance(liked_object, Post): parent_thread = liked_object.thread
        elif isinstance(liked_object, Comment): parent_thread = liked_object.post.thread
        if parent_thread and parent_thread.is_hidden and not user.is_staff:
            raise serializers.ValidationError(_("Cannot like content in a hidden thread."))


        # For create (POST): Check if already liked
        # For delete (handled by view), this validation isn't for the serializer itself
        if self.context['request'].method == 'POST':
            if Like.objects.filter(user=user, content_type=content_type, object_id=object_id).exists():
                raise serializers.ValidationError(_("You have already liked this item."))
        
        data['content_type'] = content_type # Add the actual ContentType object for save()
        return data

    def create(self, validated_data):
        # User is set from request context in the view
        # content_type_model and object_id are popped because 'content_type' is now in validated_data
        validated_data.pop('content_type_model', None)
        return Like.objects.create(user=self.context['request'].user, **validated_data)


# --- Report Serializer ---
class ReportSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and viewing Reports.
    """
    reporter = SimpleUserSerializer(read_only=True) # Reporter is set from request context
    resolved_by = SimpleUserSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    # For creation, accept model name and object ID
    content_type_model = serializers.CharField(write_only=True, help_text=_("Model name of the reported object (e.g., 'thread', 'post', 'comment')."))
    object_id = serializers.UUIDField(write_only=True)

    # For display, show details of the reported object
    reported_object_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Report
        fields = [
            'id', 'reporter', 'content_type_model', 'object_id', 'reported_object_details',
            'reason', 'status', 'status_display', 'moderator_notes', 'resolved_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'reporter', 'reported_object_details', 'status_display', 'resolved_by',
            'created_at', 'updated_at'
        ]
        # Writable fields on create: content_type_model, object_id, reason
        # Writable fields on update (by admin): status, moderator_notes

    def get_reported_object_details(self, obj):
        if obj.reported_object:
            # Provide a simple representation, e.g., title or snippet
            if hasattr(obj.reported_object, 'title'):
                return {'type': obj.content_type.model, 'id': str(obj.object_id), 'title': obj.reported_object.title}
            if hasattr(obj.reported_object, 'content'):
                content_snippet = (obj.reported_object.content[:75] + '...') if len(obj.reported_object.content) > 75 else obj.reported_object.content
                return {'type': obj.content_type.model, 'id': str(obj.object_id), 'content_snippet': content_snippet}
            return {'type': obj.content_type.model, 'id': str(obj.object_id)}
        return None

    def validate_content_type_model(self, value):
        value = value.lower()
        allowed_models = ['thread', 'post', 'comment'] # Extend as needed
        if value not in allowed_models:
            raise serializers.ValidationError(_(f"Reporting is not supported for model '{value}'. Allowed: {', '.join(allowed_models)}"))
        return value

    def validate(self, data):
        content_type_model = data.get('content_type_model')
        object_id = data.get('object_id')
        user = self.context['request'].user

        try:
            app_label = 'community'
            content_type = ContentType.objects.get(app_label=app_label, model=content_type_model)
        except ContentType.DoesNotExist:
            raise serializers.ValidationError({'content_type_model': _(f"Invalid model type '{content_type_model}'.")})

        ModelClass = content_type.model_class()
        if not ModelClass.objects.filter(pk=object_id).exists():
            raise serializers.ValidationError({'object_id': _(f"{ModelClass.__name__} with ID '{object_id}' not found.")})

        # Check for hidden content (using CanInteractWithContent logic as a guide)
        reported_object = ModelClass.objects.get(pk=object_id)
        if hasattr(reported_object, 'is_hidden') and reported_object.is_hidden and not user.is_staff:
            raise serializers.ValidationError(_("Cannot report hidden content."))
        
        parent_thread = None
        if isinstance(reported_object, Post): parent_thread = reported_object.thread
        elif isinstance(reported_object, Comment): parent_thread = reported_object.post.thread
        if parent_thread and parent_thread.is_hidden and not user.is_staff:
            raise serializers.ValidationError(_("Cannot report content in a hidden thread."))


        # Prevent duplicate pending reports by the same user for the same object
        if self.context['request'].method == 'POST':
            if Report.objects.filter(reporter=user, content_type=content_type, object_id=object_id, status='pending').exists():
                raise serializers.ValidationError(_("You have already submitted a pending report for this item."))
        
        data['content_type'] = content_type
        return data

    def create(self, validated_data):
        validated_data.pop('content_type_model', None) # Already processed into 'content_type'
        return Report.objects.create(reporter=self.context['request'].user, **validated_data)

    def update(self, instance, validated_data):
        # Only allow certain fields to be updated, typically by admins (status, moderator_notes)
        # This logic is better enforced in the view's permission or by restricting fields here.
        # For example, if only status and moderator_notes are updatable by admin:
        # instance.status = validated_data.get('status', instance.status)
        # instance.moderator_notes = validated_data.get('moderator_notes', instance.moderator_notes)
        # instance.resolved_by = self.context['request'].user # If admin is resolving
        # instance.save()
        # return instance
        return super().update(instance, validated_data) # Default allows updating fields in serializer
