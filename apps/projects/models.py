from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

# from apps.courses.models import Course # Use string literal 'courses.Course' for ForeignKey

class ProjectCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Category Name"), max_length=150, unique=True)
    slug = models.SlugField(_("Slug"), max_length=170, unique=True, blank=True, help_text=_("URL-friendly identifier, auto-generated."))
    description = models.TextField(_("Description"), blank=True, null=True)
    icon_url = models.URLField(_("Icon URL"), blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Project Category")
        verbose_name_plural = _("Project Categories")
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class ProjectTag(models.Model): # If this is a distinct tag system for projects
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Tag Name"), max_length=100, unique=True)
    slug = models.SlugField(_("Slug"), max_length=120, unique=True, blank=True, help_text=_("URL-friendly identifier, auto-generated."))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Project Tag")
        verbose_name_plural = _("Project Tags")
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Project(models.Model):
    DIFFICULTY_CHOICES = [
        ('beginner', _('Beginner')),
        ('intermediate', _('Intermediate')),
        ('advanced', _('Advanced')),
    ]
    SOURCE_CHOICES = [
        ('platform', _('Platform Created')),
        ('ai_generated', _('AI Generated Suggestion')),
        ('user_custom', _('User Custom Project')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("Project Title"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=300, unique=True, blank=True, help_text=_("URL-friendly identifier, auto-generated.")) # Increased length
    subtitle = models.CharField(_("Short Subtitle/Summary"), max_length=255, blank=True, null=True)
    description_html = models.TextField(_("Detailed Project Description (HTML)"))
    
    category = models.ForeignKey(
        ProjectCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='projects'
    )
    tags = models.ManyToManyField(ProjectTag, blank=True, related_name='projects_tagged') # Use this distinct ProjectTag
    
    difficulty_level = models.CharField(
        _("Difficulty Level"),
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default='intermediate'
    )
    estimated_duration = models.CharField(
        _("Estimated Duration"),
        max_length=100,
        blank=True, null=True,
        help_text=_("e.g., '20 hours', '2 weeks'")
    )
    learning_objectives_html = models.TextField(
        _("Learning Objectives (HTML)"),
        blank=True, null=True,
        help_text=_("What the user will learn or achieve.")
    )
    requirements_html = models.TextField(
        _("Prerequisites/Requirements (HTML)"),
        blank=True, null=True,
        help_text=_("Skills or tools needed before starting.")
    )
    cover_image_url = models.URLField(_("Cover Image URL"), max_length=1024, blank=True, null=True)
    
    associated_courses = models.ManyToManyField(
        'courses.Course', # String literal to avoid circular import
        blank=True,
        related_name='related_projects',
        help_text=_("Courses that provide knowledge for this project.")
    )
    
    ai_generated_spec_json = models.JSONField(
        _("AI Generated Specification (JSON)"),
        null=True, blank=True, default=dict,
        help_text=_("Raw specification from the AI project generator, if applicable.")
    )
    project_source = models.CharField(
        _("Project Source"),
        max_length=20,
        choices=SOURCE_CHOICES,
        default='platform'
    )

    is_published = models.BooleanField(
        _("Published"), default=True,
        help_text=_("Whether the project is available for users to start.")
    )
    is_featured = models.BooleanField(_("Featured"), default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='projects_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")
        ordering = ['-is_featured', '-created_at', 'title']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            original_slug = self.slug
            counter = 1
            while Project.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class UserProject(models.Model):
    STATUS_CHOICES = [
        ('not_started', _('Not Started')),
        ('active', _('Active/In Progress')),
        ('submitted', _('Submitted for Review')),
        ('completed_passed', _('Completed - Passed')),
        ('completed_failed', _('Completed - Failed')),
        ('archived', _('Archived')),
    ]
    SUBMISSION_TYPE_CHOICES = [
        ('json_data', _('JSON Data (e.g., code files)')),
        ('repo_url', _('Repository URL')),
        ('gcs_link', _('Google Cloud Storage Link')),
        ('text_input', _('Direct Text Input')), # For very simple submissions
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_projects')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='user_project_instances')
    
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default='not_started'
    )
    
    started_at = models.DateTimeField(_("Started At"), null=True, blank=True)
    submitted_at = models.DateTimeField(_("Submitted At"), null=True, blank=True)
    completed_at = models.DateTimeField(_("Completed At"), null=True, blank=True)
    
    submission_type = models.CharField(
        _("Submission Type"),
        max_length=20,
        choices=SUBMISSION_TYPE_CHOICES,
        null=True, blank=True
    )
    # Flexible field for submission; its interpretation depends on submission_type.
    submission_data_json = models.JSONField( 
        _("Submission Data/Link (JSON)"),
        null=True, blank=True, default=dict,
        help_text=_("Stores submitted files as JSON, or a URL, or other structured data.")
    )
    # project_repository_url field was merged into submission_data_json conceptually
    # or can be a specific field if repo_url is the primary submission method.
    # For now, submission_data_json can hold {"repository_url": "..."} if submission_type is 'repo_url'.

    assessment_score = models.FloatField(
        _("Assessment Score (0-100)"),
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    assessment_feedback_html = models.TextField(
        _("Assessment Feedback (HTML)"),
        blank=True, null=True
    )
    ai_assessment_details_json = models.JSONField( # More detailed raw output from AI assessment
        _("AI Raw Assessment Details (JSON)"),
        null=True, blank=True, default=dict
    )
    last_accessed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("User Project")
        verbose_name_plural = _("User Projects")
        unique_together = ('user', 'project')
        ordering = ['user', '-last_accessed_at']

    def __str__(self):
        return f"{self.user.email}'s work on '{self.project.title}' ({self.get_status_display()})"
