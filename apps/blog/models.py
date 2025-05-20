from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.utils import timezone
import uuid

# Assuming ProjectTag is the shared tag model. If you create a separate BlogTag, import that instead.
from apps.projects.models import ProjectTag as Tag

class BlogCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Category Name"), max_length=150, unique=True)
    slug = models.SlugField(_("Slug"), max_length=170, unique=True, blank=True, help_text=_("URL-friendly identifier, auto-generated."))
    description = models.TextField(_("Description"), blank=True, null=True)
    display_order = models.PositiveIntegerField(_("Display Order"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Blog Category")
        verbose_name_plural = _("Blog Categories")
        ordering = ['display_order', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Author(models.Model): # Optional Author model for non-Uplas users or extended author profiles
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # If Uplas user is deleted, Author profile can remain if desired
        null=True, blank=True,
        related_name='blog_author_profile_ext' # Distinct related_name
    )
    display_name = models.CharField(_("Author Display Name"), max_length=150)
    bio = models.TextField(_("Author Bio"), blank=True, null=True)
    avatar_url = models.URLField(_("Author Avatar URL (override)"), blank=True, null=True)
    # Add other fields like social media links if needed

    def __str__(self):
        return self.display_name or (self.user.get_full_name() if self.user else _("Unknown Author"))

    @property
    def get_display_name(self):
        if self.display_name:
            return self.display_name
        if self.user:
            return self.user.full_name or self.user.email
        return _("Anonymous Author")

    @property
    def get_avatar_url(self):
        if self.avatar_url:
            return self.avatar_url
        if self.user and hasattr(self.user, 'profile') and self.user.profile.profile_picture_url: # Assuming User.profile for main avatar
            return self.user.profile.profile_picture_url
        if self.user and hasattr(self.user, 'profile_picture_url') and self.user.profile_picture_url: # If avatar is directly on User
            return self.user.profile_picture_url
        return None # Or a placeholder URL

class BlogPost(models.Model):
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('published', _('Published')),
        ('archived', _('Archived')), # For old posts no longer prominent
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("Post Title"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=300, unique=True, blank=True, help_text=_("URL-friendly identifier, auto-generated."))
    
    # Primary author is a Uplas User.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep post if author Uplas account is deleted
        null=True, # But an author must be assigned
        related_name='blog_posts' # Default related_name from User to BlogPost
    )
    # Optional override or guest author details using the Author model
    author_profile_override = models.ForeignKey(
        Author,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='authored_blog_posts',
        help_text=_("Use this for guest authors or to override Uplas user author details.")
    )

    category = models.ForeignKey(
        BlogCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='blog_posts'
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='blog_posts') # Changed related_name for clarity
    
    featured_image_url = models.URLField(_("Featured Image URL"), max_length=1024, blank=True, null=True)
    content_html = models.TextField(_("Content (HTML format)"))
    excerpt = models.TextField(
        _("Excerpt/Summary"),
        max_length=350, # Typical meta description length + buffer
        blank=True, null=True,
        help_text=_("Short summary for list views and SEO. Auto-generated if blank.")
    )

    status = models.CharField(_("Status"), max_length=10, choices=STATUS_CHOICES, default='draft')
    publish_date = models.DateTimeField(_("Publish Date"), null=True, blank=True, db_index=True)
    
    meta_description = models.CharField(_("Meta Description (SEO)"), max_length=160, blank=True, null=True)
    meta_keywords = models.CharField(_("Meta Keywords (SEO)"), max_length=255, blank=True, null=True, help_text=_("Comma-separated keywords"))

    view_count = models.PositiveIntegerField(_("View Count"), default=0)
    # comment_count = models.PositiveIntegerField(_("Approved Comment Count"), default=0) # Can be added and updated by signals

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Blog Post")
        verbose_name_plural = _("Blog Posts")
        ordering = ['-status', '-publish_date', '-created_at'] # Show published, then by date

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            original_slug = self.slug
            counter = 1
            while BlogPost.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        
        if self.status == 'published' and not self.publish_date:
            self.publish_date = timezone.now()
        # If changed from published to draft, clear publish_date? Or keep for record?
        # For now, publish_date is only set when first published.
        # else if self.status != 'published' and self.publish_date:
        # self.publish_date = None 

        if not self.excerpt and self.content_html:
            from django.utils.html import strip_tags
            stripped_content = strip_tags(self.content_html)
            self.excerpt = (stripped_content[:297] + "...") if len(stripped_content) > 300 else stripped_content
        
        if not self.meta_description and self.excerpt: # Populate meta_description from excerpt if empty
            self.meta_description = self.excerpt[:160]

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def display_author_name(self):
        if self.author_profile_override:
            return self.author_profile_override.get_display_name
        if self.author:
            return self.author.full_name or self.author.email
        return _("Anonymous")

    @property
    def display_author_avatar_url(self):
        if self.author_profile_override:
            return self.author_profile_override.get_avatar_url
        if self.author:
            if hasattr(self.author, 'profile') and self.author.profile.profile_picture_url:
                return self.author.profile.profile_picture_url
            if hasattr(self.author, 'profile_picture_url') and self.author.profile_picture_url:
                return self.author.profile_picture_url
        return None # Or placeholder


class BlogComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='comments')
    
    author = models.ForeignKey( # Uplas User if logged in
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True # Null if guest comment
    )
    author_name = models.CharField(_("Author Name (Guest)"), max_length=100, blank=True)
    author_email = models.EmailField(_("Author Email (Guest, Optional)"), blank=True, null=True) # Not displayed publicly
    
    content = models.TextField(_("Comment Content"))
    parent_comment = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='replies'
    )
    
    is_approved = models.BooleanField(_("Approved"), default=True, help_text=_("Admin can unapprove comments."))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Blog Comment")
        verbose_name_plural = _("Blog Comments")
        ordering = ['created_at']

    def __str__(self):
        commenter = self.author.email if self.author else self.author_name
        return f"Comment by {commenter or 'Anonymous'} on '{self.post.title}'"
    
    @property
    def commenter_display_name(self):
        if self.author:
            return self.author.full_name or self.author.email # Use email as fallback if no full_name
        return self.author_name or _("Anonymous")
    
    @property
    def commenter_avatar_url(self):
        if self.author:
            if hasattr(self.author, 'profile') and self.author.profile.profile_picture_url:
                return self.author.profile.profile_picture_url
            if hasattr(self.author, 'profile_picture_url') and self.author.profile_picture_url:
                 return self.author.profile_picture_url
        # Return a default/placeholder avatar for guests or users without one
        return f"https://ui-avatars.com/api/?name={slugify(self.commenter_display_name)}&background=random"


# Optional: Signal to update BlogPost.comment_count if you add that field
# from django.db.models.signals import post_save, post_delete
# from django.dispatch import receiver

# @receiver([post_save, post_delete], sender=BlogComment)
# def update_blog_post_comment_count(sender, instance, **kwargs):
#     post = instance.post
#     post.comment_count = post.comments.filter(is_approved=True).count()
#     post.save(update_fields=['comment_count'])
