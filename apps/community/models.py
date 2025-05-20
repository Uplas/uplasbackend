from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.utils import timezone # Import timezone
import uuid

# Assuming a shared Tag model from projects app for consistency.
# If community needs its own distinct tags, define a new CommunityTag model here.
from apps.projects.models import ProjectTag # Using ProjectTag as a common Tag model

class CommunityCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Category Name"), max_length=150, unique=True)
    slug = models.SlugField(_("Slug"), max_length=170, unique=True, blank=True, help_text=_("URL-friendly identifier, auto-generated."))
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Group Name"), max_length=200, unique=True)
    slug = models.SlugField(_("Slug"), max_length=220, unique=True, blank=True, help_text=_("URL-friendly identifier, auto-generated."))
    description = models.TextField(_("Group Description"))
    group_icon_url = models.URLField(_("Group Icon URL"), blank=True, null=True)
    cover_image_url = models.URLField(_("Cover Image URL"), blank=True, null=True)
    
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, # Group persists if creator account is deleted/unlinked
        related_name='created_community_groups'
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='community_groups_joined', # Changed related_name to avoid clash with User.community_groups if that's used elsewhere
        through='GroupMembership',
        blank=True
    )
    
    is_private = models.BooleanField(
        _("Private Group"),
        default=False,
        help_text=_("If true, requires approval or invitation to join. Public otherwise.")
    )
    # admins = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='admin_of_community_groups', blank=True) # Consider for more granular admin roles within group

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Community Group")
        verbose_name_plural = _("Community Groups")
        ordering = ['-created_at', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            original_slug = self.slug
            counter = 1
            while CommunityGroup.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class GroupMembership(models.Model):
    ROLE_CHOICES = [
        ('member', _('Member')),
        ('admin', _('Admin')), # Group admin, can manage members/settings
        ('moderator', _('Moderator')), # Can moderate posts within group
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='group_memberships')
    group = models.ForeignKey(CommunityGroup, on_delete=models.CASCADE, related_name='group_memberships') # This related_name is fine for Group -> Membership
    date_joined = models.DateTimeField(auto_now_add=True)
    role = models.CharField(_("Role in Group"), max_length=10, choices=ROLE_CHOICES, default='member')

    class Meta:
        unique_together = ('user', 'group')
        verbose_name = _("Group Membership")
        verbose_name_plural = _("Group Memberships")
        ordering = ['group__name', 'user__email']


    def __str__(self):
        return f"{self.user.email} in {self.group.name} as {self.get_role_display()}"

class CommunityPost(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='community_posts_authored') # Changed related_name
    title = models.CharField(_("Post Title"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=300, unique=True, blank=True, help_text=_("URL-friendly identifier, auto-generated with random suffix."))
    content_html = models.TextField(_("Content (HTML)"))
    
    category = models.ForeignKey(
        CommunityCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='community_posts' # Changed related_name
    )
    group = models.ForeignKey(
        CommunityGroup,
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        related_name='community_posts' # Changed related_name
    )
    tags = models.ManyToManyField(ProjectTag, blank=True, related_name='community_posts_tagged')
    
    view_count = models.PositiveIntegerField(_("View Count"), default=0)
    reaction_count = models.PositiveIntegerField(_("Reaction Count"), default=0)
    comment_count = models.PositiveIntegerField(_("Comment Count"), default=0)

    is_pinned = models.BooleanField(_("Pinned"), default=False, help_text=_("Pinned to top of category/group/forum"))
    is_closed = models.BooleanField(_("Closed for Comments"), default=False)
    
    last_activity_at = models.DateTimeField(_("Last Activity At"), default=timezone.now) # Default to now, updated by comments/edits
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True) # This will update on every save

    class Meta:
        verbose_name = _("Community Post")
        verbose_name_plural = _("Community Posts")
        ordering = ['-is_pinned', '-last_activity_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            if not base_slug: # Handle empty titles for slug generation
                base_slug = "post"
            random_suffix = uuid.uuid4().hex[:6]
            self.slug = f"{base_slug}-{random_suffix}"
            # Ensure uniqueness, especially important if titles can be very similar
            while CommunityPost.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                random_suffix = uuid.uuid4().hex[:6]
                self.slug = f"{base_slug}-{random_suffix}"
        
        # If being updated (not new) and content changed, or just general update, update last_activity_at
        # However, created_at will handle initial last_activity if new.
        # For edits, updated_at itself reflects edit time. last_activity_at is more for new comments.
        # If new comment makes this save, comment's save should update this post's last_activity_at
        if not self._state.adding and self.updated_at: # if instance is being updated
             # Let PostComment signal handle last_activity_at for comments.
             # For direct post edits, updated_at serves a similar purpose.
             # If an explicit "bump" on edit is desired for last_activity_at:
             # self.last_activity_at = timezone.now()
             pass

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class PostComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='post_comments_authored') # Changed related_name
    content_html = models.TextField(_("Comment Content (HTML)"))
    
    parent_comment = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='replies'
    )
    reaction_count = models.PositiveIntegerField(_("Reaction Count"), default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Post Comment")
        verbose_name_plural = _("Post Comments")
        ordering = ['created_at']

    def __str__(self):
        author_display = self.author.email if self.author else "Anonymous"
        return f"Comment by {author_display} on '{self.post.title}'"
    
    # Signal will handle updating post's last_activity_at and comment_count

class PostReaction(models.Model):
    REACTION_CHOICES = [
        ('like', _('Like')),
        ('heart', _('Heart')),
        ('thumbs_up', _('Thumbs Up')),
        ('laugh', _('Laugh')),
        ('insightful', _('Insightful')),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='post_reactions_given') # Changed related_name
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='reactions', null=True, blank=True)
    comment = models.ForeignKey(PostComment, on_delete=models.CASCADE, related_name='reactions', null=True, blank=True)
    reaction_type = models.CharField(_("Reaction Type"), max_length=20, choices=REACTION_CHOICES, default='like')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Post Reaction")
        verbose_name_plural = _("Post Reactions")
        unique_together = [
            ('user', 'post', 'reaction_type'),
            ('user', 'comment', 'reaction_type')
        ]
        constraints = [
            models.CheckConstraint(
                name="community_postreaction_either_post_or_comment", # Renamed constraint for clarity
                check=(
                    (models.Q(post__isnull=False) & models.Q(comment__isnull=True)) |
                    (models.Q(post__isnull=True) & models.Q(comment__isnull=False))
                ),
                violation_error_message="Reaction must be for either a post or a comment, not both or neither."
            )
        ]

    def __str__(self):
        target_info = ""
        if self.post:
            target_info = f"post ID {self.post_id}"
        elif self.comment:
            target_info = f"comment ID {self.comment_id}"
        return f"{self.user.email} {self.get_reaction_type_display()}d {target_info}"
    
    # Signal will handle updating reaction_count on post/comment


# Signals for denormalized counts and last_activity_at
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=PostComment)
@receiver(post_delete, sender=PostComment)
def update_post_on_comment_change(sender, instance, **kwargs):
    post = instance.post
    post.comment_count = post.comments.count()
    # Update last_activity_at only if this comment is the newest activity (or post itself was just edited)
    # The most recent comment or the post's own updated_at should define last_activity_at
    latest_comment_time = post.comments.aggregate(latest=models.Max('created_at'))['latest']
    
    new_last_activity = post.updated_at # Start with post's own update time
    if latest_comment_time:
        if new_last_activity is None or latest_comment_time > new_last_activity:
            new_last_activity = latest_comment_time
    
    # If post was just created, created_at could be the last activity if no comments
    if new_last_activity is None and post.created_at:
        new_last_activity = post.created_at

    if post.last_activity_at != new_last_activity and new_last_activity is not None:
        post.last_activity_at = new_last_activity
    
    post.save(update_fields=['comment_count', 'last_activity_at'])


@receiver(post_save, sender=PostReaction)
@receiver(post_delete, sender=PostReaction)
def update_reactionable_item_reaction_count(sender, instance, **kwargs):
    target = instance.post if instance.post else instance.comment
    if target:
        target.reaction_count = target.reactions.count()
        target.save(update_fields=['reaction_count'])
