from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.html import format_html
from django.contrib.contenttypes.admin import GenericTabularInline # For GenericForeignKey relationships

from .models import Forum, Thread, Post, Comment, Like, Report

# --- Inlines (Optional, but can be useful) ---

class ThreadInline(admin.TabularInline): # Or StackedInline
    model = Thread
    extra = 0 # Don't show empty forms for adding new threads here
    fields = ('title_link', 'author_link', 'reply_count', 'like_count', 'is_pinned', 'is_closed', 'is_hidden', 'last_activity_at')
    readonly_fields = ('title_link', 'author_link', 'reply_count', 'like_count', 'last_activity_at')
    can_delete = True # Admins might want to delete threads from forum view
    show_change_link = False # title_link provides this

    def title_link(self, obj):
        if obj.pk:
            link = reverse("admin:community_thread_change", args=[obj.id])
            return format_html('<a href="{}">{}</a>', link, obj.title)
        return "-"
    title_link.short_description = _('Thread Title')

    def author_link(self, obj):
        if obj.author:
            link = reverse("admin:auth_user_change", args=[obj.author.id]) # Adjust if custom user admin URL
            return format_html('<a href="{}">{}</a>', link, obj.author.email or obj.author.username)
        return _("N/A")
    author_link.short_description = _('Author')

    def has_add_permission(self, request, obj=None):
        return False # Threads are usually created via frontend or specific admin actions

class PostInline(admin.TabularInline):
    model = Post
    extra = 0
    fields = ('author_link', 'content_summary', 'like_count', 'is_hidden', 'created_at')
    readonly_fields = ('author_link', 'content_summary', 'like_count', 'created_at')
    can_delete = True
    show_change_link = True

    def author_link(self, obj):
        if obj.author:
            link = reverse("admin:auth_user_change", args=[obj.author.id])
            return format_html('<a href="{}">{}</a>', link, obj.author.email or obj.author.username)
        return _("N/A")
    author_link.short_description = _('Author')

    def content_summary(self, obj):
        return (obj.content[:75] + '...') if len(obj.content) > 75 else obj.content
    content_summary.short_description = _('Content')

    def has_add_permission(self, request, obj=None):
        return False # Posts are usually created via frontend

class CommentInline(admin.TabularInline): # If Comments are implemented and managed this way
    model = Comment
    extra = 0
    fields = ('author_link', 'content_summary', 'like_count', 'is_hidden', 'created_at')
    readonly_fields = ('author_link', 'content_summary', 'like_count', 'created_at')
    can_delete = True
    show_change_link = True

    def author_link(self, obj):
        if obj.author:
            link = reverse("admin:auth_user_change", args=[obj.author.id])
            return format_html('<a href="{}">{}</a>', link, obj.author.email or obj.author.username)
        return _("N/A")
    author_link.short_description = _('Author')

    def content_summary(self, obj):
        return (obj.content[:75] + '...') if len(obj.content) > 75 else obj.content
    content_summary.short_description = _('Content')

    def has_add_permission(self, request, obj=None):
        return False


class LikeInline(GenericTabularInline): # For GenericForeignKey
    model = Like
    extra = 0
    fields = ('user_link', 'created_at')
    readonly_fields = ('user_link', 'created_at')
    can_delete = True # Admins might want to remove a like

    def user_link(self, obj):
        if obj.user:
            link = reverse("admin:auth_user_change", args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', link, obj.user.email or obj.user.username)
        return "-"
    user_link.short_description = _('User')

    def has_add_permission(self, request, obj=None):
        return False # Likes are created by users via API


# --- ModelAdmin configurations ---

@admin.register(Forum)
class ForumAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'display_order', 'thread_count', 'post_count', 'is_moderated', 'created_at')
    list_filter = ('is_moderated', 'created_at')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'thread_count', 'post_count', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description', 'display_order', 'is_moderated')}),
        (_('Statistics (Read-Only)'), {'fields': ('thread_count', 'post_count')}),
        (_('Timestamps (Read-Only)'), {'fields': ('created_at', 'updated_at')}),
    )
    inlines = [ThreadInline] # Show threads within this forum

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'forum_link', 'author_link', 'reply_count', 'view_count', 'like_count',
        'is_pinned', 'is_closed', 'is_hidden', 'last_activity_at', 'created_at'
    )
    list_filter = ('forum', 'is_pinned', 'is_closed', 'is_hidden', 'author', 'created_at', 'last_activity_at')
    search_fields = ('title', 'slug', 'content', 'author__email', 'author__username', 'forum__name')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('id', 'reply_count', 'view_count', 'like_count', 'last_activity_at', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'forum', 'author')}),
        (_('Content'), {'fields': ('content',)}),
        (_('Status & Moderation'), {'fields': ('is_pinned', 'is_closed', 'is_hidden')}),
        (_('Statistics (Read-Only)'), {'fields': ('reply_count', 'view_count', 'like_count')}),
        (_('Timestamps (Read-Only)'), {'fields': ('last_activity_at', 'created_at', 'updated_at')}),
        # ('Related Content', {'fields': ('related_course', 'related_project')}) # If these fields are added
    )
    inlines = [PostInline, LikeInline] # Show posts and likes for this thread
    actions = ['pin_threads', 'unpin_threads', 'close_threads', 'open_threads', 'hide_threads', 'unhide_threads']
    list_select_related = ('forum', 'author')

    def forum_link(self, obj):
        link = reverse("admin:community_forum_change", args=[obj.forum.id])
        return format_html('<a href="{}">{}</a>', link, obj.forum.name)
    forum_link.short_description = _('Forum')
    forum_link.admin_order_field = 'forum__name'

    def author_link(self, obj):
        if obj.author:
            link = reverse("admin:auth_user_change", args=[obj.author.id])
            return format_html('<a href="{}">{}</a>', link, obj.author.email or obj.author.username)
        return _("N/A")
    author_link.short_description = _('Author')
    author_link.admin_order_field = 'author__email'

    def pin_threads(self, request, queryset): queryset.update(is_pinned=True, updated_at=timezone.now())
    pin_threads.short_description = _("Pin selected threads")
    def unpin_threads(self, request, queryset): queryset.update(is_pinned=False, updated_at=timezone.now())
    unpin_threads.short_description = _("Unpin selected threads")
    def close_threads(self, request, queryset): queryset.update(is_closed=True, updated_at=timezone.now())
    close_threads.short_description = _("Close selected threads")
    def open_threads(self, request, queryset): queryset.update(is_closed=False, updated_at=timezone.now())
    open_threads.short_description = _("Open selected threads")
    def hide_threads(self, request, queryset): queryset.update(is_hidden=True, updated_at=timezone.now())
    hide_threads.short_description = _("Hide selected threads")
    def unhide_threads(self, request, queryset): queryset.update(is_hidden=False, updated_at=timezone.now())
    unhide_threads.short_description = _("Unhide selected threads")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('content_summary', 'thread_link', 'author_link', 'like_count', 'is_hidden', 'created_at')
    list_filter = ('thread__forum', 'is_hidden', 'author', 'created_at')
    search_fields = ('content', 'author__email', 'author__username', 'thread__title')
    readonly_fields = ('id', 'like_count', 'created_at', 'updated_at')
    fields = ('thread', 'author', 'content', 'is_hidden') # Control field order
    inlines = [CommentInline, LikeInline] # Show comments and likes for this post
    actions = ['hide_posts', 'unhide_posts']
    list_select_related = ('thread', 'thread__forum', 'author')

    def content_summary(self, obj):
        return (obj.content[:100] + '...') if len(obj.content) > 100 else obj.content
    content_summary.short_description = _('Content')

    def thread_link(self, obj):
        link = reverse("admin:community_thread_change", args=[obj.thread.id])
        return format_html('<a href="{}">{}</a>', link, obj.thread.title)
    thread_link.short_description = _('Thread')
    thread_link.admin_order_field = 'thread__title'

    def author_link(self, obj):
        if obj.author:
            link = reverse("admin:auth_user_change", args=[obj.author.id])
            return format_html('<a href="{}">{}</a>', link, obj.author.email or obj.author.username)
        return _("N/A")
    author_link.short_description = _('Author')
    author_link.admin_order_field = 'author__email'

    def hide_posts(self, request, queryset): queryset.update(is_hidden=True, updated_at=timezone.now())
    hide_posts.short_description = _("Hide selected posts")
    def unhide_posts(self, request, queryset): queryset.update(is_hidden=False, updated_at=timezone.now())
    unhide_posts.short_description = _("Unhide selected posts")


@admin.register(Comment) # If Comment model is actively used
class CommentAdmin(admin.ModelAdmin):
    list_display = ('content_summary', 'post_link', 'author_link', 'like_count', 'is_hidden', 'created_at')
    list_filter = ('post__thread__forum', 'is_hidden', 'author', 'created_at')
    search_fields = ('content', 'author__email', 'author__username', 'post__content')
    readonly_fields = ('id', 'like_count', 'created_at', 'updated_at')
    fields = ('post', 'author', 'content', 'is_hidden')
    inlines = [LikeInline] # Show likes for this comment
    actions = ['hide_comments', 'unhide_comments']
    list_select_related = ('post', 'post__thread', 'author')

    def content_summary(self, obj):
        return (obj.content[:100] + '...') if len(obj.content) > 100 else obj.content
    content_summary.short_description = _('Content')

    def post_link(self, obj):
        link = reverse("admin:community_post_change", args=[obj.post.id])
        post_summary = (obj.post.content[:30] + '...') if len(obj.post.content) > 30 else obj.post.content
        return format_html('<a href="{}">Post: {}</a>', link, post_summary)
    post_link.short_description = _('Parent Post')
    post_link.admin_order_field = 'post__content'


    def author_link(self, obj):
        if obj.author:
            link = reverse("admin:auth_user_change", args=[obj.author.id])
            return format_html('<a href="{}">{}</a>', link, obj.author.email or obj.author.username)
        return _("N/A")
    author_link.short_description = _('Author')
    author_link.admin_order_field = 'author__email'

    def hide_comments(self, request, queryset): queryset.update(is_hidden=True, updated_at=timezone.now())
    hide_comments.short_description = _("Hide selected comments")
    def unhide_comments(self, request, queryset): queryset.update(is_hidden=False, updated_at=timezone.now())
    unhide_comments.short_description = _("Unhide selected comments")


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('user_link', 'liked_object_display', 'content_type', 'object_id_display', 'created_at')
    list_filter = ('content_type', 'created_at', 'user')
    search_fields = ('user__email', 'user__username', 'object_id') # Searching GenericForeignKey is tricky
    readonly_fields = ('id', 'user', 'content_type', 'object_id', 'liked_object', 'created_at')
    list_select_related = ('user', 'content_type')

    def user_link(self, obj):
        if obj.user:
            link = reverse("admin:auth_user_change", args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', link, obj.user.email or obj.user.username)
        return "-"
    user_link.short_description = _('User')

    def liked_object_display(self, obj):
        if obj.liked_object:
            # Create a link to the admin change page of the liked object if possible
            try:
                app_label = obj.content_type.app_label
                model_name = obj.content_type.model
                admin_url = reverse(f"admin:{app_label}_{model_name}_change", args=[obj.liked_object.pk])
                return format_html('<a href="{}">{}</a>', admin_url, str(obj.liked_object))
            except Exception: # Catch potential NoReverseMatch
                return str(obj.liked_object)
        return _("N/A (Object might be deleted)")
    liked_object_display.short_description = _('Liked Object')

    def object_id_display(self, obj):
        return str(obj.object_id)
    object_id_display.short_description = _('Object ID')


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('reported_object_display', 'reporter_link', 'reason_summary', 'status', 'resolved_by_link', 'created_at', 'updated_at')
    list_filter = ('status', 'content_type', 'created_at', 'reporter', 'resolved_by')
    search_fields = ('reason', 'reporter__email', 'resolved_by__email', 'moderator_notes', 'object_id')
    readonly_fields = ('id', 'reporter', 'content_type', 'object_id', 'reported_object', 'created_at', 'updated_at')
    fieldsets = (
        (_('Report Details'), {'fields': ('reporter', 'content_type', 'object_id', 'reported_object_link', 'reason')}),
        (_('Moderation'), {'fields': ('status', 'moderator_notes', 'resolved_by')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    list_select_related = ('reporter', 'resolved_by', 'content_type')
    actions = ['resolve_reports_action_taken', 'resolve_reports_no_action', 'dismiss_reports']
    autocomplete_fields = ['reporter', 'resolved_by'] # For easier selection

    def reported_object_link(self, obj):
        if obj.reported_object:
            try:
                app_label = obj.content_type.app_label
                model_name = obj.content_type.model
                admin_url = reverse(f"admin:{app_label}_{model_name}_change", args=[obj.reported_object.pk])
                return format_html('<a href="{}">View {} ({})</a>', admin_url, model_name.capitalize(), str(obj.reported_object))
            except Exception:
                return f"{obj.content_type.model.capitalize()}: {str(obj.reported_object)}"
        return _("N/A (Object might be deleted)")
    reported_object_link.short_description = _('Reported Content')
    
    # Add reported_object_link to readonly_fields in fieldsets to display it
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # Add reported_object_link to the first fieldset if obj exists
        if obj:
            fieldsets[0][1]['fields'] = ('reporter', 'content_type', 'object_id', 'reported_object_link', 'reason')
        return fieldsets


    def reported_object_display(self, obj):
        if obj.reported_object:
            return f"{obj.content_type.model.capitalize()}: {str(obj.reported_object)[:50]}..."
        return _("N/A")
    reported_object_display.short_description = _('Reported Content')

    def reporter_link(self, obj):
        if obj.reporter:
            link = reverse("admin:auth_user_change", args=[obj.reporter.id])
            return format_html('<a href="{}">{}</a>', link, obj.reporter.email or obj.reporter.username)
        return _("N/A")
    reporter_link.short_description = _('Reporter')

    def resolved_by_link(self, obj):
        if obj.resolved_by:
            link = reverse("admin:auth_user_change", args=[obj.resolved_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.resolved_by.email or obj.resolved_by.username)
        return "-"
    resolved_by_link.short_description = _('Resolved By')

    def reason_summary(self, obj):
        return (obj.reason[:75] + '...') if len(obj.reason) > 75 else obj.reason
    reason_summary.short_description = _('Reason')

    def resolve_reports_action_taken(self, request, queryset):
        queryset.update(status='resolved_action_taken', resolved_by=request.user, updated_at=timezone.now())
    resolve_reports_action_taken.short_description = _("Resolve selected reports (Action Taken)")

    def resolve_reports_no_action(self, request, queryset):
        queryset.update(status='resolved_no_action', resolved_by=request.user, updated_at=timezone.now())
    resolve_reports_no_action.short_description = _("Resolve selected reports (No Action)")

    def dismiss_reports(self, request, queryset):
        queryset.update(status='dismissed', resolved_by=request.user, updated_at=timezone.now())
    dismiss_reports.short_description = _("Dismiss selected reports as invalid")

