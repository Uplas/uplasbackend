import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

# Assuming you might want to link community content to courses or projects
# from apps.courses.models import Course # Example
# from apps.projects.models import Project # Example

# Choices for Report Status
REPORT_STATUS_CHOICES = [
    ('pending', _('Pending Review')),
    ('resolved_no_action', _('Resolved - No Action Taken')),
    ('resolved_action_taken', _('Resolved - Action Taken')),
    ('dismissed', _('Dismissed as Invalid')),
]

class Forum(models.Model):
    """
    Represents a forum or a main discussion category.
    e.g., "General Discussion", "Python Help", "Project Showcases"
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, unique=True, verbose_name=_('Forum Name'))
    slug = models.SlugField(max_length=170, unique=True, verbose_name=_('Slug'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))
    # icon = models.ImageField(upload_to='forum_icons/', blank=True, null=True) # Optional
    display_order = models.PositiveIntegerField(default=0, verbose_name=_('Display Order'))
    
    # Denormalized counts (updated by signals)
    thread_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Thread Count'))
    post_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Post Count')) # Total posts in all threads

    # Moderation settings for this forum
    is_moderated = models.BooleanField(default=True, verbose_name=_('Is Moderated'))
    # created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='forums_created') # Admin/Staff
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Forum')
        verbose_name_plural = _('Forums')
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

class Thread(models.Model):
    """
    Represents a discussion thread within a Forum.
    Started by a user with an initial post (which is the thread's content itself).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='threads', verbose_name=_('Forum'))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep thread if author is deleted, but mark author as null
        null=True,
        related_name='threads_started',
        verbose_name=_('Author')
    )
    title = models.CharField(max_length=255, verbose_name=_('Thread Title'))
    slug = models.SlugField(max_length=280, unique=True, verbose_name=_('Slug')) # Ensure unique slug for threads
    
    # The initial content of the thread (the first post)
    content = models.TextField(verbose_name=_('Initial Post Content'))
    
    # Denormalized counts (updated by signals)
    reply_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Reply Count')) # Number of posts excluding the initial one
    view_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('View Count'))
    like_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Like Count (for thread itself)'))
    
    is_pinned = models.BooleanField(default=False, verbose_name=_('Is Pinned')) # Sticky thread
    is_closed = models.BooleanField(default=False, verbose_name=_('Is Closed')) # No more replies allowed
    is_hidden = models.BooleanField(default=False, verbose_name=_('Is Hidden by Moderator')) # Soft delete

    # Optional: Link to a specific course or project if the thread is about it
    # related_course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.SET_NULL, related_name='forum_threads')
    # related_project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name='forum_threads')

    last_activity_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Last Activity At')) # Updated when new post or thread created/edited
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))


    class Meta:
        verbose_name = _('Thread')
        verbose_name_plural = _('Threads')
        ordering = ['-is_pinned', '-last_activity_at'] # Pinned threads first, then by recent activity

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Update last_activity_at on each save (creation or update of thread content)
        self.last_activity_at = timezone.now()
        super().save(*args, **kwargs)


class Post(models.Model):
    """
    Represents a reply (post) within a Thread.
    The initial content of a thread is stored in Thread.content.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name='posts', verbose_name=_('Thread'))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep post if author is deleted
        null=True,
        related_name='posts_created',
        verbose_name=_('Author')
    )
    content = models.TextField(verbose_name=_('Post Content'))
    
    # Denormalized counts (updated by signals)
    like_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Like Count'))
    # comment_count = models.PositiveIntegerField(default=0, editable=False) # If posts can have direct comments

    is_hidden = models.BooleanField(default=False, verbose_name=_('Is Hidden by Moderator')) # Soft delete
    
    # For threaded replies to posts (nested comments) - optional complexity
    # parent_post = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Post (Reply)')
        verbose_name_plural = _('Posts (Replies)')
        ordering = ['created_at'] # Chronological order within a thread

    def __str__(self):
        return f"Reply by {self.author.email if self.author else 'Anonymous'} in '{self.thread.title}' at {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class Comment(models.Model):
    """
    Represents a comment on a Post (if allowing comments on replies).
    Or, could be used for comments on Blog posts or other content types using GenericForeignKey.
    For simplicity here, let's assume comments are on Posts.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments', verbose_name=_('Parent Post'))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='post_comments_made',
        verbose_name=_('Author')
    )
    content = models.TextField(verbose_name=_('Comment Content'))
    is_hidden = models.BooleanField(default=False, verbose_name=_('Is Hidden by Moderator'))
    like_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Like Count'))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Comment on Post')
        verbose_name_plural = _('Comments on Posts')
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.email if self.author else 'Anonymous'} on post {self.post.id}"


class Like(models.Model):
    """
    Represents a like on a Thread, Post, or Comment.
    Uses a GenericForeignKey to point to the liked object.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes_given')
    
    # Generic Foreign Key setup
    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.contrib.contenttypes.models import ContentType
    
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField() # Ensure liked objects use UUIDs or adjust type
    liked_object = GenericForeignKey('content_type', 'object_id')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Like')
        verbose_name_plural = _('Likes')
        # Ensure a user can only like an object once
        unique_together = [['user', 'content_type', 'object_id']]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} likes {self.liked_object}"


class Report(models.Model):
    """
    Allows users to report Threads, Posts, or Comments for moderation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep report if reporter is deleted
        null=True,
        related_name='reports_made'
    )
    
    # Generic Foreign Key setup for the reported content
    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.contrib.contenttypes.models import ContentType
    
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE) # Type of object reported (Thread, Post, Comment)
    object_id = models.UUIDField() # ID of the specific reported object
    reported_object = GenericForeignKey('content_type', 'object_id')
    
    reason = models.TextField(verbose_name=_('Reason for Reporting'))
    status = models.CharField(
        max_length=30,
        choices=REPORT_STATUS_CHOICES,
        default='pending',
        verbose_name=_('Report Status')
    )
    # Admin/Moderator who handled this report
    moderator_notes = models.TextField(blank=True, null=True, verbose_name=_('Moderator Notes'))
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reports_resolved',
        verbose_name=_('Resolved By (Moderator)')
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Reported At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Last Updated At')) # When status changes

    class Meta:
        verbose_name = _('Reported Content')
        verbose_name_plural = _('Reported Contents')
        # A user might report the same object multiple times if not handled,
        # or you might want to prevent duplicate active reports for the same object by the same user.
        # unique_together = [['reporter', 'content_type', 'object_id', 'status']] # If only one pending report per user/object
        ordering = ['-created_at']

    def __str__(self):
        return f"Report by {self.reporter.email if self.reporter else 'Anonymous'} on {self.content_type.model} {self.object_id} ({self.get_status_display()})"


# --- Signals for denormalization and activity updates ---

@receiver(post_save, sender=Thread)
@receiver(post_delete, sender=Thread)
def update_forum_thread_count(sender, instance, **kwargs):
    forum = instance.forum
    if forum: # Forum might be null if CASCADE on delete happened from Forum itself
        forum.thread_count = Thread.objects.filter(forum=forum, is_hidden=False).count()
        # Post count for forum is more complex, needs to sum posts from all its threads
        # This might be better handled by a periodic task or more specific signals from Post.
        forum.save(update_fields=['thread_count'])

@receiver(post_save, sender=Post)
@receiver(post_delete, sender=Post)
def update_thread_reply_count_and_activity(sender, instance, **kwargs):
    thread = instance.thread
    if thread: # Thread might be null if CASCADE on delete happened from Thread itself
        thread.reply_count = Post.objects.filter(thread=thread, is_hidden=False).count()
        thread.last_activity_at = timezone.now() # Update on new post or post deletion (activity change)
        thread.save(update_fields=['reply_count', 'last_activity_at'])
        
        # Update Forum's total post count (initial thread content + replies)
        if thread.forum:
            total_posts_in_forum = 0
            for t in Thread.objects.filter(forum=thread.forum, is_hidden=False):
                total_posts_in_forum += 1 # For the thread's initial content
                total_posts_in_forum += t.posts.filter(is_hidden=False).count()
            thread.forum.post_count = total_posts_in_forum
            thread.forum.save(update_fields=['post_count'])


@receiver(post_save, sender=Like)
@receiver(post_delete, sender=Like)
def update_like_count(sender, instance, **kwargs):
    liked_object = instance.liked_object
    if liked_object and hasattr(liked_object, 'like_count'):
        # Ensure the liked_object is one of our models that has 'like_count'
        if isinstance(liked_object, (Thread, Post, Comment)):
            liked_object.like_count = Like.objects.filter(
                content_type=instance.content_type,
                object_id=instance.object_id
            ).count()
            liked_object.save(update_fields=['like_count'])

# Consider signals for Comment count on Post if that's added.
