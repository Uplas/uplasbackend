from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.utils import timezone # Ensure timezone is imported
import uuid

# Using choices from settings if defined globally, otherwise define here or in a choices.py
# For simplicity, if CURRENCY_CHOICES is defined in settings.users, we assume it's accessible
# via settings.CURRENCY_CHOICES. If not, define it here.
# from apps.users.models import CURRENCY_CHOICES # Or define locally if not in settings

# Local CURRENCY_CHOICES if not globally in settings from users app
# (Assuming they are already defined in settings.py as per users app setup)
# CURRENCY_CHOICES = [
#     ('USD', _('USD - US Dollar')),
#     ('EUR', _('EUR - Euro')),
#     # ... add more if needed
# ]


class CourseCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Category Name"), max_length=150, unique=True)
    slug = models.SlugField(_("Slug"), max_length=170, unique=True, blank=True, help_text=_("URL-friendly identifier"))
    description = models.TextField(_("Description"), blank=True, null=True)
    icon_url = models.URLField(_("Icon URL"), blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Course Category")
        verbose_name_plural = _("Course Categories")
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Course(models.Model):
    DIFFICULTY_CHOICES = [
        ('beginner', _('Beginner')),
        ('intermediate', _('Intermediate')),
        ('advanced', _('Advanced')),
        ('expert', _('Expert')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("Course Title"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=270, unique=True, blank=True, help_text=_("URL-friendly identifier for the course"))
    subtitle = models.CharField(_("Subtitle/Short Description"), max_length=255, blank=True, null=True)
    description_html = models.TextField(_("Detailed Description (HTML format)"))
    category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses')
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courses_taught',
        help_text=_("Lead instructor or author")
    )
    
    price = models.DecimalField(_("Price"), max_digits=10, decimal_places=2, default=0.00)
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        choices=settings.CURRENCY_CHOICES if hasattr(settings, 'CURRENCY_CHOICES') else [('USD', 'USD')], # Fallback if not in settings
        default='USD'
    )
    
    cover_image_url = models.URLField(_("Cover Image URL"), max_length=1024, blank=True, null=True)
    promo_video_url = models.URLField(_("Promotional Video URL"), max_length=1024, blank=True, null=True)
    
    difficulty_level = models.CharField(
        _("Difficulty Level"),
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default='beginner'
    )
    estimated_duration = models.CharField(
        _("Estimated Duration"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("e.g., '10 hours', '3 weeks'")
    )
    
    learning_objectives = models.JSONField(
        _("What You'll Learn / Learning Objectives"),
        default=list,
        blank=True,
        help_text=_("List of key takeaways or skills gained.")
    )
    requirements = models.JSONField(
        _("Prerequisites/Requirements"),
        default=list,
        blank=True,
        help_text=_("List of prerequisites or necessary tools/knowledge.")
    )
    target_audience = models.JSONField(
        _("Who is this course for?"),
        default=list,
        blank=True
    )

    is_published = models.BooleanField(_("Published"), default=False, help_text=_("Whether the course is live and visible to users"))
    published_date = models.DateTimeField(_("Published Date"), null=True, blank=True)
    
    average_rating = models.FloatField(_("Average Rating"), default=0.0)
    total_enrollments = models.PositiveIntegerField(_("Total Enrollments"), default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Course")
        verbose_name_plural = _("Courses")
        ordering = ['-created_at', 'title']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            original_slug = self.slug
            counter = 1
            # Ensure slug uniqueness if creating
            while Course.objects.filter(slug=self.slug).exclude(pk=self.pk).exists(): # Exclude self if updating
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        if self.is_published and not self.published_date:
            self.published_date = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class Module(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(_("Module Title"), max_length=255)
    description = models.TextField(_("Module Description"), blank=True, null=True)
    order = models.PositiveIntegerField(_("Module Order"), default=0, help_text=_("Order of the module within the course"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Module")
        verbose_name_plural = _("Modules")
        ordering = ['course', 'order', 'title']
        unique_together = ('course', 'order')

    def __str__(self):
        return f"{self.course.title} - Module {self.order}: {self.title}"

class Topic(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('text', _('Text Article')),
        ('video', _('Video Lesson')),
        ('quiz', _('Quiz/Assessment')),
        ('assignment', _('Coding Assignment')), # Simplified: details in text_content_html or external link
        ('external_resource', _('External Resource')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='topics')
    title = models.CharField(_("Topic Title"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=300, unique=True, blank=True, help_text=_("URL-friendly identifier for the topic")) # Increased length
    order = models.PositiveIntegerField(_("Topic Order"), default=0, help_text=_("Order of the topic within the module"))
    
    content_type = models.CharField(
        _("Content Type"),
        max_length=20,
        choices=CONTENT_TYPE_CHOICES,
        default='text'
    )
    text_content_html = models.TextField(_("Text Content (HTML)"), blank=True, null=True, help_text=_("Used if content_type is 'text', 'assignment'"))
    video_url = models.URLField(_("Video URL"), blank=True, null=True, help_text=_("Used if content_type is 'video'"))
    external_resource_url = models.URLField(_("External Resource URL"), blank=True, null=True, help_text=_("Used if content_type is 'external_resource'"))
    
    estimated_duration_minutes = models.PositiveIntegerField(
        _("Estimated Duration (minutes)"),
        null=True, blank=True,
        help_text=_("Estimated time to complete this topic in minutes")
    )
    is_previewable = models.BooleanField(
        _("Previewable"),
        default=False,
        help_text=_("Can users view this topic before enrolling/purchasing?")
    )

    supports_ai_tutor = models.BooleanField(_("Supports AI Tutor"), default=True)
    supports_tts = models.BooleanField(_("Supports Text-to-Speech"), default=True)
    supports_ttv = models.BooleanField(_("Supports Text-to-Video"), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Topic")
        verbose_name_plural = _("Topics")
        ordering = ['module__course__title', 'module__order', 'order', 'title'] # Order globally then locally
        unique_together = ('module', 'order')

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            # Ensure slug is unique, possibly by appending module/course identifiers or random chars if needed for global uniqueness
            module_prefix = slugify(self.module.title)[:20]
            course_prefix = slugify(self.module.course.title)[:20]
            self.slug = f"{course_prefix}-{module_prefix}-{base_slug}"
            original_slug = self.slug
            counter = 1
            while Topic.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.module.title} - Topic {self.order}: {self.title}"

class Quiz(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.OneToOneField(Topic, on_delete=models.CASCADE, related_name='quiz_details', limit_choices_to={'content_type': 'quiz'})
    title = models.CharField(_("Quiz Title"), max_length=255, blank=True)
    description = models.TextField(_("Quiz Description/Instructions"), blank=True, null=True)
    pass_mark_percentage = models.PositiveSmallIntegerField(
        _("Pass Mark Percentage"),
        default=70,
        help_text=_("Minimum percentage to pass the quiz")
    )
    time_limit_minutes = models.PositiveIntegerField(_("Time Limit (minutes)"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Quiz")
        verbose_name_plural = _("Quizzes")

    def save(self, *args, **kwargs):
        if not self.title and self.topic:
            self.title = f"Quiz for: {self.topic.title}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title or f"Quiz for Topic ID: {self.topic_id}"

class Question(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('multiple_choice', _('Multiple Choice')), # Multiple correct options possible (checkboxes)
        ('single_choice', _('Single Choice')),   # Only one correct option (radio buttons)
        ('true_false', _('True/False')),
        ('short_answer', _('Short Answer (Text Input)')),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(_("Question Text"))
    question_type = models.CharField(
        _("Question Type"),
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default='single_choice'
    )
    order = models.PositiveIntegerField(_("Question Order"), default=0)
    explanation = models.TextField(_("Explanation for Answer"), blank=True, null=True, help_text=_("Shown after attempt or review"))
    points = models.PositiveSmallIntegerField(_("Points"), default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")
        ordering = ['quiz', 'order']

    def __str__(self):
        return f"Q{self.order}: {self.text[:50]}... ({self.quiz.title})"

class AnswerOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(_("Option Text"), max_length=500)
    is_correct = models.BooleanField(_("Is Correct Answer"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Answer Option")
        verbose_name_plural = _("Answer Options")
        ordering = ['question', 'id'] # Or 'question', '?' to randomize display order

    def __str__(self):
        return f"{self.text} (Correct: {self.is_correct})"

class UserCourseEnrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(_("Completed At"), null=True, blank=True)
    
    progress_percentage = models.PositiveSmallIntegerField(_("Progress Percentage"), default=0)
    last_accessed_topic = models.ForeignKey('Topic', on_delete=models.SET_NULL, null=True, blank=True, related_name='last_accessed_by_enrollments')

    class Meta:
        verbose_name = _("User Course Enrollment")
        verbose_name_plural = _("User Course Enrollments")
        unique_together = ('user', 'course')
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.user.username} enrolled in {self.course.title}"

    def update_progress(self):
        total_topics_count = Topic.objects.filter(module__course=self.course).count()
        if total_topics_count == 0:
            self.progress_percentage = 100 if not self.course.modules.exists() else 0
            if self.progress_percentage == 100 and not self.completed_at :
                 self.completed_at = timezone.now()
            self.save(update_fields=['progress_percentage', 'completed_at'])
            return

        completed_topics_count = UserTopicAttempt.objects.filter(
            enrollment=self,
            is_completed=True
        ).count()
        
        self.progress_percentage = int((completed_topics_count / total_topics_count) * 100)
        
        if self.progress_percentage >= 100 and not self.completed_at:
            self.completed_at = timezone.now()
            # TODO: Consider emitting a signal for course completion (e.g., for certificates, XP)
            
        self.save(update_fields=['progress_percentage', 'completed_at'])

class UserTopicAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(UserCourseEnrollment, on_delete=models.CASCADE, related_name='topic_attempts')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='user_attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='topic_attempts_direct')

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(_("Completed At"), null=True, blank=True)
    is_completed = models.BooleanField(_("Is Completed"), default=False)
    
    score = models.FloatField(_("Score (percentage for quizzes)"), null=True, blank=True) # For quizzes, 0-100
    passed = models.BooleanField(_("Passed (quiz/assignment)"), null=True, blank=True)
    
    answer_history_json = models.JSONField(_("Answer History (JSON for Quizzes)"), null=True, blank=True)
    
    last_accessed_at = models.DateTimeField(auto_now=True)

    # Store original completion status to check if it changed for progress update
    _original_is_completed = None

    class Meta:
        verbose_name = _("User Topic Attempt")
        verbose_name_plural = _("User Topic Attempts")
        unique_together = ('enrollment', 'topic')
        ordering = ['enrollment', 'topic__module__order', 'topic__order']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_is_completed = self.is_completed

    def save(self, *args, **kwargs):
        if self.enrollment and self.user_id != self.enrollment.user_id: # Ensure user consistency
             raise ValueError("UserTopicAttempt user must match enrollment user.")
        
        is_status_changed = self.is_completed != self._original_is_completed
        super().save(*args, **kwargs)
        
        if is_status_changed or self._state.adding: # If status changed or new attempt
            if self.enrollment:
                self.enrollment.update_progress()
        self._original_is_completed = self.is_completed # Update original status after save

    def __str__(self):
        return f"{self.user.username} - {self.topic.title} (Completed: {self.is_completed})"

class Review(models.Model):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews_given')
    rating = models.PositiveSmallIntegerField(_("Rating (1-5)"), choices=RATING_CHOICES)
    comment = models.TextField(_("Comment"), blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Review")
        verbose_name_plural = _("Reviews")
        unique_together = ('course', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"Review for {self.course.title} by {self.user.username} ({self.rating} stars)"

# Signals for updating denormalized counts/ratings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=Review)
@receiver(post_delete, sender=Review)
def update_course_average_rating(sender, instance, **kwargs):
    course = instance.course
    # Recalculate average rating
    reviews = Review.objects.filter(course=course)
    if reviews.exists():
        avg_rating = reviews.aggregate(models.Avg('rating'))['rating__avg']
        course.average_rating = round(avg_rating, 2) if avg_rating is not None else 0.0
    else:
        course.average_rating = 0.0
    course.save(update_fields=['average_rating'])

@receiver(post_save, sender=UserCourseEnrollment)
@receiver(post_delete, sender=UserCourseEnrollment)
def update_course_total_enrollments(sender, instance, **kwargs):
    course = instance.course
    course.total_enrollments = UserCourseEnrollment.objects.filter(course=course).count()
    course.save(update_fields=['total_enrollments'])
