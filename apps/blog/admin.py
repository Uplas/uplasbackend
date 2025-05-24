from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html

from .models import BlogCategory, BlogPostTag, BlogPost, BlogComment

# --- Inlines ---
class BlogCommentInline(admin.TabularInline): # Or StackedInline for more space
    model = BlogComment
    extra = 0 # Don't show empty forms for adding new ones here by default
    fields = ('author_link', 'content_summary', 'is_approved', 'is_hidden_by_moderator', 'created_at')
    readonly_fields = ('author_link', 'content_summary', 'created_at')
    can_delete = True # Admins might want to delete comments
    show_change_link = True # Allow navigating to the BlogComment admin page

    def author_link(self, obj):
        if obj.author:
            link = reverse("admin:auth_user_change", args=[obj.author.id]) # Adjust if custom user admin URL
            return format_html('<a href="{}">{}</a>', link, obj.author.email or obj.author.username)
        return _("Anonymous/Deleted")
    author_link.short_description = _('Author')

    def content_summary(self, obj):
        return (obj.content[:75] + '...') if len(obj.content) > 75 else obj.content
    content_summary.short_description = _('Comment')

    def has_add_permission(self, request, obj=None):
        # Comments are usually added via frontend, not directly inline in admin for a post
        return False

# --- ModelAdmin configurations ---

@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    """
    Admin configuration for the BlogCategory model.
    """
    list_display = ('name', 'slug', 'post_count_display', 'created_at')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'post_count', 'created_at', 'updated_at') # post_count is denormalized

    def post_count_display(self, obj):
        return obj.post_count
    post_count_display.short_description = _('Published Post Count')
    post_count_display.admin_order_field = 'post_count'


@admin.register(BlogPostTag)
class BlogPostTagAdmin(admin.ModelAdmin):
    """
    Admin configuration for the BlogPostTag model.
    """
    list_display = ('name', 'slug', 'post_tag_count', 'created_at')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'created_at')

    def post_tag_count(self, obj):
        return obj.blog_posts.count() # Counts all posts with this tag, regardless of status
    post_tag_count.short_description = _('Number of Posts')


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    """
    Admin configuration for the BlogPost model.
    """
    list_display = (
        'title', 'author_link', 'category_link', 'status', 'published_at_formatted',
        'view_count', 'like_count', 'comment_count_display', 'created_at'
    )
    list_filter = ('status', 'category', 'tags', 'author', 'published_at', 'created_at')
    search_fields = ('title', 'slug', 'excerpt', 'content_markdown', 'author__email', 'author__username', 'category__name', 'tags__name')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = (
        'id', 'view_count', 'like_count', 'comment_count', #'content_html',
        'created_at', 'updated_at' # published_at can be set manually or by status change
    )
    filter_horizontal = ('tags',) # Better UI for ManyToManyField
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'author', 'category', 'tags')}),
        (_('Content'), {'fields': ('excerpt', 'content_markdown', 'featured_image')}), # Add 'content_html' if used and readonly
        (_('Publication'), {'fields': ('status', 'published_at')}),
        (_('SEO (Optional)'), {'classes': ('collapse',), 'fields': ('meta_title', 'meta_description')}),
        (_('Statistics (Read-Only)'), {'classes': ('collapse',), 'fields': ('view_count', 'like_count', 'comment_count')}),
        (_('Timestamps (Read-Only)'), {'classes': ('collapse',), 'fields': ('created_at', 'updated_at')}),
    )
    inlines = [BlogCommentInline]
    actions = ['publish_selected_posts', 'unpublish_selected_posts', 'archive_selected_posts']
    list_select_related = ('author', 'category') # Optimize list view queries
    autocomplete_fields = ['author', 'category'] # For easier selection

    def author_link(self, obj):
        if obj.author:
            link = reverse("admin:auth_user_change", args=[obj.author.id])
            return format_html('<a href="{}">{}</a>', link, obj.author.email or obj.author.username)
        return _("N/A")
    author_link.short_description = _('Author')
    author_link.admin_order_field = 'author__email'

    def category_link(self, obj):
        if obj.category:
            link = reverse("admin:blog_blogcategory_change", args=[obj.category.id])
            return format_html('<a href="{}">{}</a>', link, obj.category.name)
        return "-"
    category_link.short_description = _('Category')
    category_link.admin_order_field = 'category__name'

    def published_at_formatted(self, obj):
        return obj.published_at.strftime("%Y-%m-%d %H:%M") if obj.published_at else "-"
    published_at_formatted.short_description = _('Published At')
    published_at_formatted.admin_order_field = 'published_at'

    def comment_count_display(self, obj):
        return obj.comment_count
    comment_count_display.short_description = _('Comments')
    comment_count_display.admin_order_field = 'comment_count'


    def publish_selected_posts(self, request, queryset):
        queryset.update(status='published', published_at=timezone.now(), updated_at=timezone.now())
    publish_selected_posts.short_description = _("Publish selected posts")

    def unpublish_selected_posts(self, request, queryset): # Move to draft
        queryset.update(status='draft', updated_at=timezone.now()) # published_at might be kept or cleared based on logic
    unpublish_selected_posts.short_description = _("Move selected posts to Draft")

    def archive_selected_posts(self, request, queryset):
        queryset.update(status='archived', updated_at=timezone.now())
    archive_selected_posts.short_description = _("Archive selected posts")

    def get_queryset(self, request):
        # Prefetch tags for efficiency in list display if showing tags directly or for filtering
        return super().get_queryset(request).prefetch_related('tags')


@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    """
    Admin configuration for the BlogComment model.
    """
    list_display = (
        'content_summary', 'author_link', 'blog_post_link', 'parent_comment_summary',
        'is_approved', 'is_hidden_by_moderator', 'like_count', 'created_at_formatted'
    )
    list_filter = ('is_approved', 'is_hidden_by_user', 'is_hidden_by_moderator', 'blog_post__category', 'author', 'created_at')
    search_fields = ('content', 'author__email', 'author__username', 'blog_post__title')
    readonly_fields = ('id', 'like_count', 'created_at', 'updated_at')
    fields = (
        'blog_post', 'author', 'parent_comment', 'content',
        'is_approved', 'is_hidden_by_user', 'is_hidden_by_moderator'
    )
    actions = ['approve_selected_comments', 'unapprove_selected_comments', 'hide_selected_comments_mod', 'unhide_selected_comments_mod']
    list_select_related = ('author', 'blog_post', 'parent_comment', 'parent_comment__author') # Optimize queries
    autocomplete_fields = ['author', 'blog_post', 'parent_comment'] # For easier selection

    def content_summary(self, obj):
        return (obj.content[:75] + '...') if len(obj.content) > 75 else obj.content
    content_summary.short_description = _('Comment')

    def author_link(self, obj):
        if obj.author:
            link = reverse("admin:auth_user_change", args=[obj.author.id])
            return format_html('<a href="{}">{}</a>', link, obj.author.email or obj.author.username)
        return _("Anonymous/Deleted")
    author_link.short_description = _('Author')
    author_link.admin_order_field = 'author__email'

    def blog_post_link(self, obj):
        link = reverse("admin:blog_blogpost_change", args=[obj.blog_post.id])
        return format_html('<a href="{}">{}</a>', link, obj.blog_post.title)
    blog_post_link.short_description = _('Blog Post')
    blog_post_link.admin_order_field = 'blog_post__title'

    def parent_comment_summary(self, obj):
        if obj.parent_comment:
            parent_author = obj.parent_comment.author.email if obj.parent_comment.author else _("Anonymous")
            summary = (obj.parent_comment.content[:30] + '...') if len(obj.parent_comment.content) > 30 else obj.parent_comment.content
            return f"Reply to: {parent_author} - \"{summary}\""
        return "-"
    parent_comment_summary.short_description = _('In Reply To')


    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%Y-%m-%d %H:%M")
    created_at_formatted.short_description = _('Commented At')
    created_at_formatted.admin_order_field = 'created_at'

    def approve_selected_comments(self, request, queryset):
        queryset.update(is_approved=True, is_hidden_by_moderator=False, updated_at=timezone.now())
    approve_selected_comments.short_description = _("Approve selected comments")

    def unapprove_selected_comments(self, request, queryset): # Effectively hides them too
        queryset.update(is_approved=False, updated_at=timezone.now())
    unapprove_selected_comments.short_description = _("Unapprove selected comments")

    def hide_selected_comments_mod(self, request, queryset):
        queryset.update(is_hidden_by_moderator=True, updated_at=timezone.now())
    hide_selected_comments_mod.short_description = _("Hide selected comments (Moderator)")

    def unhide_selected_comments_mod(self, request, queryset):
        queryset.update(is_hidden_by_moderator=False, updated_at=timezone.now())
    unhide_selected_comments_mod.short_description = _("Unhide selected comments (Moderator)")


