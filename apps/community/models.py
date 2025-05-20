from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
import uuid

# Assuming a shared Tag model, e.g., from projects app, or define a new one if needed.
from apps.projects.models import ProjectTag # Using ProjectTag as a common Tag model for now

class CommunityCategory(models.Model):
    """
    Categories for community posts/discussions, e.g., "General Discussion", "AI News", "Course Q&A".
    
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Category Name"), max_length=150, unique=True)
    slug = models.SlugField(_("Slug"), max_length=170, unique=True, blank=True)
    description = models.TextField(_("Description"), blank=True, null=True)
    icon_url = models.URLField(_("Icon URL"), blank=True, null=True)
    display_order = models.PositiveIntegerField(_("Display Order"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Community Category")
        verbose_name_plural = _("Community Categories")
        ordering = ['display_order', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class CommunityGroup(models.Model):
    """
    User-created or platform-created groups for focused discussions or study.
    
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Group Name"), max_length=200, unique=True)
    slug = models.SlugField(_("Slug"), max_length=220, unique=True, blank=True)
    description = models.TextField(_("Group Description"))
    group_icon_url = models.URLField(_("Group Icon URL"), blank=True, null=True)
    cover_image_url = models.URLField(_("Cover Image URL"), blank=True, null=True)
    
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Group persists if creator account is deleted
        null=True,
        related_name='created_community_groups'
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='community_groups',
        through='GroupMembership', # Explicit through model for join dates etc.
        blank=True
    )
    
    is_private = models.BooleanField(
        _("Private Group"),
        default=False,
        help_text=_("If true, requires approval or invitation to join. Public otherwise.")
    )
    # For private groups, an admin/moderator role within the group might be needed.
    # admins = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='admin_community_groups', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Community Group")
        verbose_name_plural = _("Community Groups")
        ordering = ['-created_at', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class GroupMembership(models.Model):
    """
    Through model for CommunityGroup members, allowing to store join date etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='group_memberships')
    group = models.ForeignKey(CommunityGroup, on_delete=models.CASCADE, related_name='group_memberships')
    date_joined = models.DateTimeField(auto_now_add=True)
    # Role could be 'member', 'admin', 'moderator'
    ROLE_CHOICES = [('member', _('Member')), ('admin', _('Admin')), ('moderator', _('Moderator'))]
    role = models.CharField(_("Role"), max_length=10, choices=ROLE_CHOICES, default='member')

    class Meta:
        unique_together = ('user', 'group')
        verbose_name = _("Group Membership")
        verbose_name_plural = _("Group Memberships")

    def __str__(self):
        return f"{self.user.username} in {self.group.name} ({self.get_role_display()})"


class CommunityPost(models.Model):
    """
    A post or discussion thread within the community, optionally tied to a category or group.
    
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_posts')
    title = models.CharField(_("Post Title"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=300, unique=True, blank=True) # Slug needs to be globally unique for posts
    content_html = models.TextField(_("Content (HTML)")) # From rich text editor
    
    category = models.ForeignKey(
        CommunityCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True, # Can be a general post not in a category
        related_name='posts'
    )
    group = models.ForeignKey(
        CommunityGroup,
        on_deletemodels.SET_NULL, # Or CASCADE if posts should be deleted with group
        null=True, blank=True, # Can be a general post not in a group
        related_name='posts'
    )
    tags = models.ManyToManyField(ProjectTag, blank=True, related_name='community_posts_tagged')
    
    view_count = models.PositiveIntegerField(_("View Count"), default=0)
    reaction_count = models.PositiveIntegerField(_("Reaction Count"), default=0) # Denormalized, e.g., total likes
    comment_count = models.PositiveIntegerField(_("Comment Count"), default=0) # Denormalized

    is_pinned = models.BooleanField(_("Pinned"), default=False, help_text=_("Pinned to top of category/group/forum"))
    is_closed = models.BooleanField(_("Closed for Comments"), default=False)
    
    last_activity_at = models.DateTimeField(_("Last Activity At"), auto_now_add=True) # Updated on new comment or edit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Community Post")
        verbose_name_plural = _("Community Posts")
        ordering = ['-is_pinned', '-last_activity_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            # Create a more unique slug, perhaps with a short ID or date part if titles aren't unique
            random_suffix = uuid.uuid4().hex[:6]
            self.slug = f"{base_slug}-{random_suffix}"
            while CommunityPost.objects.filter(slug=self.slug).exists():
                random_suffix = uuid.uuid4().hex[:6]
                self.slug = f"{base_slug}-{random_suffix}"

        if not self._state.adding: # If updating
            self.last_activity_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class PostComment(models.Model):
    """
    A comment on a CommunityPost. Can be threaded.
    
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='post_comments')
    content_html = models.TextField(_("Comment Content (HTML)"))
    
    parent_comment = models.ForeignKey(
        'self',
        on_delete=models.CASCADE, # If parent is deleted, children are also deleted
        null=True, blank=True,
        related_name='replies'
    )
    reaction_count = models.PositiveIntegerField(_("Reaction Count"), default=0) # Denormalized

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Post Comment")
        verbose_name_plural = _("Post Comments")
        ordering = ['created_at'] # Order replies by creation time

    def __str__(self):
        return f"Comment by {self.author.username} on '{self.post.title}'"
    
    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new: # Update post's last_activity_at and comment_count
            self.post.last_activity_at = self.created_at
            self.post.comment_count = self.post.comments.count() # Recalculate
            self.post.save(update_fields=['last_activity_at', 'comment_count'])


class PostReaction(models.Model):
    """
    User reactions to posts or comments (e.g., like, upvote, heart).
    
    """
    REACTION_CHOICES = [
        ('like', _('Like')),
        ('heart', _('Heart')),
        ('thumbs_up', _('Thumbs Up')),
        # Add more as needed
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='post_reactions')
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='reactions', null=True, blank=True)
    comment = models.ForeignKey(PostComment, on_delete=models.CASCADE, related_name='reactions', null=True, blank=True)
    reaction_type = models.CharField(_("Reaction Type"), max_length=20, choices=REACTION_CHOICES, default='like')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Post Reaction")
        verbose_name_plural = _("Post Reactions")
        unique_together = [
            ('user', 'post', 'reaction_type'),       # User can only react once per type to a post
            ('user', 'comment', 'reaction_type')     # User can only react once per type to a comment
        ]
        constraints = [
            models.CheckConstraint(
                name="either_post_or_comment_not_both",
                check=(
                    (models.Q(post__isnull=False) & models.Q(comment__isnull=True)) |
                    (models.Q(post__isnull=True) & models.Q(comment__isnull=False))
                )
            )
        ]

    def __str__(self):
        target = self.post if self.post else self.comment
        return f"{self.user.username} {self.reaction_type}d {target}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update reaction_count on post/comment
        if self.post:
            self.post.reaction_count = self.post.reactions.count()
            self.post.save(update_fields=['reaction_count'])
        elif self.comment:
            self.comment.reaction_count = self.comment.reactions.count()
            self.comment.save(update_fields=['reaction_count'])

from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone # Import timezone

@receiver(post_delete, sender=PostReaction)
def update_reaction_count_on_delete(sender, instance, **kwargs):
    if instance.post:
        instance.post.reaction_count = instance.post.reactions.count()
        instance.post.save(update_fields=['reaction_count'])
    elif instance.comment:
        instance.comment.reaction_count = instance.comment.reactions.count()
        instance.comment.save(update_fields=['reaction_count'])

@receiver(post_delete, sender=PostComment)
def update_post_comment_count_on_delete(sender, instance, **kwargs):
    if instance.post:
        instance.post.comment_count = instance.post.comments.count()
        instance.post.save(update_fields=['comment_count'])
