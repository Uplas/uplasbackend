from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.utils import timezone # Import timezone
import uuid

# Assuming a shared Tag model, e.g., from projects app
from apps.projects.models import ProjectTag as Tag # Using ProjectTag as a common Tag model

class BlogCategory(models.Model):
    """
    Categories for blog posts.
    
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Category Name"), max_length=150, unique=True)
    slug = models.SlugField(_("Slug"), max_length=170, unique=True, blank=True)
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

class Author(models.Model): # Optional: If authors are not always Uplas Users or need more fields
    """
    Represents an author for blog posts, could be linked to a User or be a separate entity.
    For simplicity, we'll link to User, but this allows expansion.
    (Guide mentions "ForeignKey to User or a simpler Author model")
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='blog_author_profile')
    display_name = models.CharField(_("Display Name"), max_length=150) # If different from user.full_name
    bio = models.TextField(_("Author Bio"), blank=True, null=True)
    avatar_url = models.URLField(_("Author Avatar URL"), blank=True, null=True) # Override user.profile_picture_url if needed

    def __str__(self):
        return self.display_name or (self.user.full_name if self.user else "Unknown Author")

class BlogPost(models.Model):
    """
    Represents a blog post.
    
    """
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('published', _('Published')),
        ('archived', _('Archived')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("Post Title"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=300, unique=True, blank=True)
    
    author = models.ForeignKey( # Can be direct User or Author model
        settings.AUTH_USER_MODEL, # Simpler: directly use the User model for authors
        on_delete=models.SET_NULL,
        null=True, # Post can remain if author account is deleted
        related_name='blog_posts_authored'
    )
    # author_override = models.ForeignKey(Author, on_delete=models.SET_NULL, null=True, blank=True) # If using separate Author model

    category = models.ForeignKey(
        BlogCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='blog_posts'
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='blog_posts_tagged')
    
    featured_image_url = models.URLField(_("Featured Image URL"), max_length=1024, blank=True, null=True)
    # content_html (or Markdown)
    content_html = models.TextField(_("Content (HTML format)")) # From rich text editor
    excerpt = models.TextField(_("Excerpt/Summary"), blank=True, null=True, help_text=_("Short summary for list views"))

    status = models.CharField(_("Status"), max_length=10, choices=STATUS_CHOICES, default='draft')
    publish_date = models.DateTimeField(_("Publish Date"), null=True, blank=True) # Set when status becomes 'published'
    
    # SEO Fields
    meta_description = models.CharField(_("Meta Description (SEO)"), max_length=160, blank=True, null=True)
    meta_keywords = models.CharField(_("Meta Keywords (SEO)"), max_length=255, blank=True, null=True, help_text=_("Comma-separated keywords"))

    view_count = models.PositiveIntegerField(_("View Count"), default=0) # Simple view counter
    # reaction_count, comment_count if adding reactions/detailed comment tracking like community
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Blog Post")
        verbose_name_plural = _("Blog Posts")
        ordering = ['-publish_date', '-created_at'] # Show newest published posts first

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            original_slug = self.slug
            queryset = BlogPost.objects.filter(slug=original_slug).exists()
            counter = 1
            while queryset:
                self.slug = f"{original_slug}-{counter}"
                counter += 1
                queryset = BlogPost.objects.filter(slug=self.slug).exists()
        
        if self.status == 'published' and not self.publish_date:
            self.publish_date = timezone.now()
        elif self.status != 'published':
            self.publish_date = None # Clear publish date if not published

        if not self.excerpt and self.content_html: # Auto-generate excerpt if empty
            from django.utils.html import strip_tags
            self.excerpt = strip_tags(self.content_html)[:200] + "..." if len(strip_tags(self.content_html)) > 200 else strip_tags(self.content_html)

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class BlogComment(models.Model):
    """
    Comments on blog posts.
    
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='comments')
    
    # Option 1: If only authenticated users can comment
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep comment if user is deleted
        null=True, blank=True # Allow anonymous if author_name is used
    )
    # Option 2: For guest comments (as per guide: author_name, author_email)
    author_name = models.CharField(_("Author Name (if guest)"), max_length=100, blank=True)
    author_email = models.EmailField(_("Author Email (if guest, optional)"), blank=True, null=True)
    
    content = models.TextField(_("Comment Content"))
    parent_comment = models.ForeignKey( # For threaded comments
        'self',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='replies'
    )
    
    is_approved = models.BooleanField(_("Approved"), default=True, help_text=_("Moderated comments can be hidden if not approved"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Blog Comment")
        verbose_name_plural = _("Blog Comments")
        ordering = ['created_at']

    def __str__(self):
        commenter = self.author.username if self.author else self.author_name
        return f"Comment by {commenter or 'Anonymous'} on '{self.post.title}'"
    
    @property
    def commenter_display_name(self):
        if self.author:
            return self.author.full_name or self.author.username
        return self.author_name or _("Anonymous")
    
    @property
    def commenter_avatar_url(self):
        if self.author and hasattr(self.author, 'profile') and self.author.profile.profile_picture_url:
            return self.author.profile.profile_picture_url
        # elif self.author and self.author.profile_picture_url: # If stored directly on user
            # return self.author.profile_picture_url
        # TODO: Add placeholder avatar for anonymous/guest comments
        return "https://via.placeholder.com/50" # Placeholder
