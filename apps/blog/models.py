import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.utils.text import slugify
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

# For GenericForeignKey if liking blog posts directly
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType


# Choices for BlogPost Status
BLOG_POST_STATUS_CHOICES = [
    ('draft', _('Draft')),
    ('published', _('Published')),
    ('archived', _('Archived')), # Kept for records but not publicly visible
]

class BlogCategory(models.Model):
    """
    Categories for blog posts (e.g., "Tutorials", "News", "Case Studies").
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, verbose_name=_('Category Name'))
    slug = models.SlugField(max_length=120, unique=True, verbose_name=_('Slug'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))
    # Denormalized count
    post_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Post Count'))
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Blog Category')
        verbose_name_plural = _('Blog Categories')
        ordering = ['name']

    def __str__(self):
        return self.name

class BlogPostTag(models.Model):
    """
    Tags for blog posts, allowing for more granular classification.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True, verbose_name=_('Tag Name'))
    slug = models.SlugField(max_length=60, unique=True, verbose_name=_('Slug'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))

    class Meta:
        verbose_name = _('Blog Post Tag')
        verbose_name_plural = _('Blog Post Tags')
        ordering = ['name']

    def __str__(self):
        return self.name


class BlogPost(models.Model):
    """
    Represents an individual blog post.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep post if author is deleted, but set author to null
        null=True,
        related_name='blog_posts_authored',
        verbose_name=_('Author')
    )
    category = models.ForeignKey(
        BlogCategory,
        on_delete=models.SET_NULL, # Keep post if category is deleted, or PROTECT
        null=True, blank=True,
        related_name='blog_posts',
        verbose_name=_('Category')
    )
    tags = models.ManyToManyField(
        BlogPostTag,
        blank=True,
        related_name='blog_posts',
        verbose_name=_('Tags')
    )
    title = models.CharField(max_length=255, verbose_name=_('Title'))
    slug = models.SlugField(max_length=280, unique=True, verbose_name=_('Slug')) # Ensure unique for URLs
    
    # Content fields
    excerpt = models.TextField(blank=True, null=True, verbose_name=_('Excerpt/Summary'), help_text=_("A short summary of the post."))
    content_markdown = models.TextField(verbose_name=_('Content (Markdown)'), help_text=_("Write content using Markdown."))
    # content_html = models.TextField(editable=False, blank=True, null=True, verbose_name=_('Content (HTML)')) # Auto-generated from Markdown
    
    featured_image = models.URLField(blank=True, null=True, verbose_name=_('Featured Image URL'))
    # For actual image uploads:
    # featured_image_file = models.ImageField(upload_to='blog_featured_images/', blank=True, null=True, verbose_name=_('Featured Image File'))

    status = models.CharField(
        max_length=20,
        choices=BLOG_POST_STATUS_CHOICES,
        default='draft',
        verbose_name=_('Status')
    )
    published_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Published At'))
    
    # Denormalized counts (updated by signals or tasks)
    view_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('View Count'))
    like_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Like Count'))
    comment_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Comment Count'))

    # SEO Fields (optional)
    meta_title = models.CharField(max_length=160, blank=True, null=True, verbose_name=_('Meta Title'))
    meta_description = models.CharField(max_length=300, blank=True, null=True, verbose_name=_('Meta Description'))

    # GenericRelation to allow Likes from the community app (or a dedicated BlogLike model)
    # Assuming 'community.Like' is the model for likes. Adjust if different.
    likes = GenericRelation('community.Like', related_query_name='blog_posts_liked')


    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Blog Post')
        verbose_name_plural = _('Blog Posts')
        ordering = ['-published_at', '-created_at'] # Published posts first, then by creation date

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            # Ensure slug uniqueness if auto-generating
            original_slug = self.slug
            counter = 1
            while BlogPost.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        elif self.status != 'published' and self.published_at is not None:
            # If moved from published to draft/archived, clear published_at or handle as per logic
            # self.published_at = None # Or keep it as historical publish date
            pass 

        # TODO: Add Markdown to HTML conversion logic here if storing content_html
        # from markdown import markdown
        # self.content_html = markdown(self.content_markdown)
        super().save(*args, **kwargs)


class BlogComment(models.Model):
    """
    Represents a comment on a BlogPost.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blog_post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name=_('Blog Post')
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep comment if author is deleted
        null=True,
        related_name='blog_comments_made',
        verbose_name=_('Author')
    )
    parent_comment = models.ForeignKey( # For threaded comments
        'self',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='replies',
        verbose_name=_('Parent Comment (for replies)')
    )
    content = models.TextField(verbose_name=_('Comment Content'))
    is_approved = models.BooleanField(default=True, verbose_name=_('Is Approved'), help_text=_("Moderator can unapprove comments."))
    is_hidden_by_user = models.BooleanField(default=False, verbose_name=_('Is Hidden by Author')) # If authors can hide their own comments
    is_hidden_by_moderator = models.BooleanField(default=False, verbose_name=_('Is Hidden by Moderator'))
    
    like_count = models.PositiveIntegerField(default=0, editable=False, verbose_name=_('Like Count'))
    # GenericRelation to allow Likes from the community app
    likes = GenericRelation('community.Like', related_query_name='blog_comments_liked')


    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Blog Comment')
        verbose_name_plural = _('Blog Comments')
        ordering = ['created_at'] # Oldest comments first for a post

    def __str__(self):
        author_email = self.author.email if self.author else _("Anonymous")
        return f"Comment by {author_email} on '{self.blog_post.title}'"
    
    @property
    def is_publicly_visible(self):
        return self.is_approved and not self.is_hidden_by_user and not self.is_hidden_by_moderator


# --- Signals for denormalization ---

@receiver(post_save, sender=BlogPost)
@receiver(post_delete, sender=BlogPost)
def update_blog_category_post_count(sender, instance, **kwargs):
    if instance.category:
        category = instance.category
        category.post_count = BlogPost.objects.filter(category=category, status='published').count() # Count only published posts
        category.save(update_fields=['post_count'])

@receiver(post_save, sender=BlogComment)
@receiver(post_delete, sender=BlogComment)
def update_blog_post_comment_count(sender, instance, **kwargs):
    blog_post = instance.blog_post
    if blog_post:
        # Count only approved and non-hidden comments
        blog_post.comment_count = BlogComment.objects.filter(
            blog_post=blog_post,
            is_approved=True,
            is_hidden_by_user=False,
            is_hidden_by_moderator=False
        ).count()
        blog_post.save(update_fields=['comment_count'])

# Signal for updating BlogPost.like_count when a 'community.Like' is saved/deleted
# This assumes 'community.Like' has a signal that can identify if the liked object is a BlogPost.
# Alternatively, if you had a dedicated BlogLike model, the signal would be on that.
# If using community.Like, its own signal should handle updating the liked_object.like_count
# as long as BlogPost has a 'like_count' field and the GenericRelation is set up.
# The community.Like signal needs to be robust enough to check:
# if isinstance(liked_object, BlogPost): liked_object.save(update_fields=['like_count'])
