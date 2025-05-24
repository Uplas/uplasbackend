from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    ProjectTag, Project, UserProject, ProjectSubmission, ProjectAssessment
)

@admin.register(ProjectTag)
class ProjectTagAdmin(admin.ModelAdmin):
    """
    Admin configuration for the ProjectTag model.
    """
    list_display = ('name', 'slug', 'project_count', 'created_at')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'created_at')

    def project_count(self, obj):
        return obj.projects.count()
    project_count.short_description = _('Number of Projects')

class UserProjectInline(admin.TabularInline): # Or StackedInline for more space
    """
    Inline for viewing UserProject instances related to a Project definition.
    Likely read-only here as UserProjects are usually created by users starting projects.
    """
    model = UserProject
    extra = 0 # Don't show empty forms for adding new ones here
    fields = ('user_link', 'status', 'started_at', 'completed_at', 'repository_url', 'live_url')
    readonly_fields = ('user_link', 'status', 'started_at', 'completed_at', 'repository_url', 'live_url')
    can_delete = False
    show_change_link = True # Allow navigating to the UserProject admin page

    def user_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.user:
            link = reverse("admin:auth_user_change", args=[obj.user.id]) # Adjust if your user model is different
            return format_html('<a href="{}">{}</a>', link, obj.user.email or obj.user.username)
        return "-"
    user_link.short_description = _('User')

    def has_add_permission(self, request, obj=None):
        return False # Don't allow adding UserProjects from Project definition inline

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Project (definition) model.
    """
    list_display = (
        'title', 'difficulty_level', 'is_published', 'ai_generated',
        'created_by_email', 'tag_list', 'user_instance_count', 'created_at'
    )
    list_filter = ('is_published', 'ai_generated', 'difficulty_level', 'technologies_used', 'created_by')
    search_fields = ('title', 'slug', 'description', 'created_by__email', 'technologies_used__name')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('id', 'created_at', 'updated_at')
    filter_horizontal = ('technologies_used',) # Better for ManyToMany
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'is_published')}),
        (_('Core Details'), {'fields': (
            'description', 'difficulty_level', 'estimated_duration_hours',
            'learning_outcomes', 'prerequisites', 'technologies_used'
        )}),
        (_('Content & Resources'), {'fields': ('guidelines', 'resources')}),
        (_('Authorship & AI'), {'fields': ('created_by', 'ai_generated', 'ai_generation_prompt')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    inlines = [UserProjectInline]
    actions = ['publish_projects', 'unpublish_projects']

    def created_by_email(self, obj):
        return obj.created_by.email if obj.created_by else _('N/A (e.g., AI)')
    created_by_email.short_description = _('Created By')
    created_by_email.admin_order_field = 'created_by__email'

    def tag_list(self, obj):
        return ", ".join([tag.name for tag in obj.technologies_used.all()])
    tag_list.short_description = _('Tags')

    def user_instance_count(self, obj):
        return obj.user_instances.count()
    user_instance_count.short_description = _('User Instances')

    def publish_projects(self, request, queryset):
        queryset.update(is_published=True)
    publish_projects.short_description = _("Publish selected project definitions")

    def unpublish_projects(self, request, queryset):
        queryset.update(is_published=False)
    unpublish_projects.short_description = _("Unpublish selected project definitions")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('technologies_used').select_related('created_by')


class ProjectSubmissionInline(admin.TabularInline):
    model = ProjectSubmission
    extra = 0
    fields = ('submitted_at', 'submission_version', 'submission_notes_summary', 'assessment_status')
    readonly_fields = ('submitted_at', 'submission_version', 'submission_notes_summary', 'assessment_status')
    can_delete = False # Usually submissions are not deleted, maybe archived
    show_change_link = True

    def submission_notes_summary(self, obj):
        if obj.submission_notes:
            return (obj.submission_notes[:75] + '...') if len(obj.submission_notes) > 75 else obj.submission_notes
        return "-"
    submission_notes_summary.short_description = _('Notes Summary')

    def assessment_status(self, obj):
        if hasattr(obj, 'assessment') and obj.assessment:
            return _("Assessed - Passed") if obj.assessment.passed else _("Assessed - Failed")
        return _("Pending Assessment")
    assessment_status.short_description = _('Assessment')

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(UserProject)
class UserProjectAdmin(admin.ModelAdmin):
    """
    Admin configuration for the UserProject (instance) model.
    """
    list_display = (
        'project_title', 'user_email', 'status', 'started_at',
        'completed_at', 'updated_at', 'submission_count'
    )
    list_filter = ('status', 'project__difficulty_level', 'project__technologies_used', 'user')
    search_fields = ('user__email', 'user__username', 'project__title', 'repository_url', 'live_url')
    readonly_fields = (
        'id', 'user', 'project', 'started_at', 'completed_at',
        'created_at', 'updated_at'
    )
    fieldsets = (
        (None, {'fields': ('user', 'project')}),
        (_('Status & Progress'), {'fields': ('status', 'started_at', 'completed_at')}),
        (_('User Provided Links'), {'fields': ('repository_url', 'live_url')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    inlines = [ProjectSubmissionInline]
    list_select_related = ('user', 'project')

    def project_title(self, obj):
        return obj.project.title
    project_title.short_description = _('Project Title')
    project_title.admin_order_field = 'project__title'

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = _('User Email')
    user_email.admin_order_field = 'user__email'

    def submission_count(self, obj):
        return obj.submissions.count()
    submission_count.short_description = _('Submissions')


class ProjectAssessmentInline(admin.TabularInline): # Or StackedInline
    model = ProjectAssessment
    extra = 0
    fields = ('assessed_by_display', 'score', 'passed', 'assessed_at', 'feedback_summary_short')
    readonly_fields = ('assessed_by_display', 'score', 'passed', 'assessed_at', 'feedback_summary_short')
    can_delete = True # Admin might need to delete a faulty assessment
    show_change_link = True

    def assessed_by_display(self, obj):
        if obj.assessed_by_ai and obj.assessor_ai_agent_name:
            return f"AI: {obj.assessor_ai_agent_name}"
        if obj.manual_assessor:
            return f"Manual: {obj.manual_assessor.get_full_name() or obj.manual_assessor.email}"
        if obj.assessed_by_ai: return "AI (Generic)"
        return _("N/A")
    assessed_by_display.short_description = _('Assessed By')

    def feedback_summary_short(self, obj):
        if obj.feedback_summary:
            return (obj.feedback_summary[:75] + '...') if len(obj.feedback_summary) > 75 else obj.feedback_summary
        return "-"
    feedback_summary_short.short_description = _('Feedback Summary')

    def has_add_permission(self, request, obj=None):
        # Assessments are usually created via API (AI) or specific admin actions, not simple inline add.
        return False


@admin.register(ProjectSubmission)
class ProjectSubmissionAdmin(admin.ModelAdmin):
    """
    Admin configuration for the ProjectSubmission model.
    """
    list_display = (
        'user_project_identifier', 'submission_version', 'submitted_at', 'assessment_status_display'
    )
    list_filter = ('user_project__project__title', 'user_project__user__email', 'submitted_at')
    search_fields = (
        'user_project__user__email', 'user_project__project__title', 'submission_notes'
    )
    readonly_fields = ('id', 'user_project', 'submitted_at', 'submission_version', 'submission_artifacts')
    fields = ('user_project', 'submitted_at', 'submission_version', 'submission_notes', 'submission_artifacts')
    inlines = [ProjectAssessmentInline] # Show the assessment directly on the submission
    list_select_related = ('user_project__user', 'user_project__project', 'assessment')

    def user_project_identifier(self, obj):
        return f"{obj.user_project.user.email} - {obj.user_project.project.title}"
    user_project_identifier.short_description = _('User Project')
    user_project_identifier.admin_order_field = 'user_project__project__title' # or user_project__user__email

    def assessment_status_display(self, obj):
        try:
            if obj.assessment: # Access related object via OneToOneField
                return _("Assessed - Passed") if obj.assessment.passed else _("Assessed - Failed")
        except ProjectAssessment.DoesNotExist:
            pass # No assessment yet
        return _("Pending Assessment")
    assessment_status_display.short_description = _('Assessment Status')


@admin.register(ProjectAssessment)
class ProjectAssessmentAdmin(admin.ModelAdmin):
    """
    Admin configuration for the ProjectAssessment model.
    """
    list_display = (
        'submission_identifier', 'assessed_by_display', 'score', 'passed', 'assessed_at'
    )
    list_filter = ('passed', 'assessed_by_ai', 'manual_assessor', 'submission__user_project__project__title')
    search_fields = (
        'submission__user_project__user__email',
        'submission__user_project__project__title',
        'assessor_ai_agent_name',
        'manual_assessor__email',
        'feedback_summary'
    )
    readonly_fields = ('id', 'submission', 'assessed_at') # Submission link should be read-only once set
    fieldsets = (
        (None, {'fields': ('submission',)}),
        (_('Assessment Details'), {'fields': (
            'assessed_by_ai', 'assessor_ai_agent_name', 'manual_assessor',
            'score', 'passed', 'feedback_summary', 'detailed_feedback'
        )}),
        (_('Timestamps'), {'fields': ('assessed_at',)}),
    )
    list_select_related = (
        'submission__user_project__user',
        'submission__user_project__project',
        'manual_assessor'
    )
    autocomplete_fields = ['submission', 'manual_assessor'] # Makes selecting easier

    def submission_identifier(self, obj):
        up = obj.submission.user_project
        return f"Sub v{obj.submission.submission_version} for: {up.user.email} - {up.project.title}"
    submission_identifier.short_description = _('Submission For')
    submission_identifier.admin_order_field = 'submission__user_project__project__title'

    def assessed_by_display(self, obj):
        if obj.assessed_by_ai and obj.assessor_ai_agent_name:
            return f"AI: {obj.assessor_ai_agent_name}"
        if obj.manual_assessor:
            return f"Manual: {obj.manual_assessor.get_full_name() or obj.manual_assessor.email}"
        if obj.assessed_by_ai: return "AI (Generic)"
        return _("N/A")
    assessed_by_display.short_description = _('Assessed By')

    # Potentially add an action to trigger re-assessment if needed

