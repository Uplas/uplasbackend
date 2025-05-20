from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

# Assuming Course model from apps.courses.models for associated_courses
# from apps.courses.models import Course # Import if not already globally accessible via settings

class ProjectCategory(models.Model):
    """
    Categories for projects, e.g., "Web Development", "Data Analysis", "Mobile App".
    
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Category Name"), max_length=150, unique=True)
    slug = models.SlugField(_("Slug"), max_length=170, unique=True, blank=True, help_text=_("URL-friendly identifier"))
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

class ProjectTag(models.Model):
    """
    Tags for projects, e.g., "Python", "JavaScript", "API Integration".
    (Implicit from `tags` field in Project model from guide)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Tag Name"), max_length=100, unique=True)
    slug = models.SlugField(_("Slug"), max_length=120, unique=True, blank=True)
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
    """
    Represents a project that users can work on.
    Can be platform-created or AI-suggested.
    
    """
    DIFFICULTY_CHOICES = [
        ('beginner', _('Beginner')),
        ('intermediate', _('Intermediate')),
        ('advanced', _('Advanced')),
    ]
    SOURCE_CHOICES = [
        ('platform', _('Platform Created')),
        ('ai_generated', _('AI Generated Suggestion')),
        ('user_custom', _('User Custom Project')), # If users can define their own
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("Project Title"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=270, unique=True, blank=True)
    subtitle = models.CharField(_("Short Subtitle/Summary"), max_length=255, blank=True, null=True)
    description_html = models.TextField(_("Detailed Project Description (HTML)"))
    
    category = models.ForeignKey(
        ProjectCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='projects'
    )
    tags = models.ManyToManyField(ProjectTag, blank=True, related_name='projects')
    
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
    
    # Link to courses that might be helpful for this project
    associated_courses = models.ManyToManyField(
        'courses.Course', # Use string literal to avoid circular import if Course model is in another app
        blank=True,
        related_name='related_projects',
        help_text=_("Courses that provide knowledge for this project.")
    )
    
    # For AI-generated projects
    ai_generated_spec_json = models.JSONField(
        _("AI Generated Specification (JSON)"),
        null=True, blank=True,
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
    is_featured = models.BooleanField(_("Featured"), default=False) # For highlighting certain projects

    created_by = models.ForeignKey( # Who authored this project spec on the platform
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
            # Ensure uniqueness if multiple projects might have similar titles
            original_slug = self.slug
            queryset = Project.objects.filter(slug=original_slug).exists()
            counter = 1
            while queryset:
                self.slug = f"{original_slug}-{counter}"
                counter += 1
                queryset = Project.objects.filter(slug=self.slug).exists()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class UserProject(models.Model):
    """
    Tracks a user's engagement, progress, and submission for a specific Project.
    
    """
    STATUS_CHOICES = [
        ('not_started', _('Not Started')), # Default when project is suggested or available
        ('active', _('Active/In Progress')), # User has started the project
        ('submitted', _('Submitted for Review')), # User submitted their work
        ('completed_passed', _('Completed - Passed')), # Assessed and passed
        ('completed_failed', _('Completed - Failed')), # Assessed and failed
        ('archived', _('Archived')), # User archived it from their active list
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
    completed_at = models.DateTimeField(_("Completed At"), null=True, blank=True) # When final status (passed/failed) is set
    
    # For storing user's project files/links
    # Option 1: Store direct GCS URLs if files are uploaded there.
    # project_files_gcs_urls = models.JSONField(
    #     _("Project Files (GCS URLs)"),
    #     null=True, blank=True,
    #     help_text=_("e.g., {'main.py': 'gcs://bucket/path/main.py', 'report.pdf': '...'}")
    # )
    # Option 2: Store links to a Git repo if user pushes to a personal repo.
    project_repository_url = models.URLField(_("Project Repository URL (e.g., GitHub)"), blank=True, null=True)
    # Option 3: Store text content directly for very small projects/scripts (less scalable for large files)
    # submitted_code_json = models.JSONField(
    #     _("Submitted Code (JSON)"),
    #     null=True, blank=True,
    #     help_text=_("e.g., {'filename1.py': 'code content...', 'filename2.js': '...'}")
    # )
    # For UProjeX IDE, the submission might be a snapshot of the IDE workspace or specific files.
    # Let's assume a JSON structure for submitted file content for now, or a link to GCS.
    submission_data_json = models.JSONField(
        _("Submission Data (JSON)"),
        null=True, blank=True,
        help_text=_("Can store file contents, links, or any structure representing the submission.")
    )

    # Assessment details from AI Agent
    assessment_score = models.FloatField(
        _("Assessment Score (0-100)"),
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    assessment_feedback_html = models.TextField(
        _("Assessment Feedback (HTML)"),
        blank=True, null=True
    )
    # ai_assessment_details_json = models.JSONField( # More detailed raw output from AI assessment
    #     _("AI Assessment Details (JSON)"),
    #     null=True, blank=True
    # )
    last_accessed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("User Project")
        verbose_name_plural = _("User Projects")
        unique_together = ('user', 'project') # User has one instance/attempt per project
        ordering = ['user', '-last_accessed_at']

    def __str__(self):
        return f"{self.user.username}'s work on '{self.project.title}' ({self.get_status_display()})"
