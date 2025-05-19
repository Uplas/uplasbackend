
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
import uuid

# Re-using User model from the users app
# from apps.users.models import User # Not needed directly, settings.AUTH_USER_MODEL is used

class CourseCategory(models.Model):
    """
    Categories for courses, e.g., "AI Fundamentals", "Machine Learning", "Data Science".
    
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Category Name"), max_length=150, unique=True)
    slug = models.SlugField(_("Slug"), max_length=170, unique=True, blank=True, help_text=_("URL-friendly identifier"))
    description = models.TextField(_("Description"), blank=True, null=True)
    icon_url = models.URLField(_("Icon URL"), blank=True, null=True) # Optional icon for the category
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
    """
    Represents a course offered on the platform.
    
    """
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
    description_html = models.TextField(_("Detailed Description (HTML format)")) # Content from frontend editor 
    category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses')
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Or PROTECT if an instructor must exist
        null=True, # Can be a platform-authored course without a specific user instructor
        blank=True,
        related_name='courses_taught',
        help_text=_("Lead instructor or author")
    )
    # instructor_name & instructor_bio from guide can be denormalized or fetched from instructor's profile 
    # For simplicity, let's assume we can fetch from User model or a dedicated InstructorProfile if needed
    
    price = models.DecimalField(_("Price"), max_digits=10, decimal_places=2, default=0.00) # 0.00 for free courses
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        choices=settings.CURRENCY_CHOICES, # Use choices from project settings
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
        _("What You'll Learn / Learning Objectives"), # Stored as a list of strings
        default=list,
        blank=True,
        help_text=_("List of key takeaways or skills gained.")
    )
    requirements = models.JSONField(
        _("Prerequisites/Requirements"), # Stored as a list of strings
        default=list,
        blank=True,
        help_text=_("List of prerequisites or necessary tools/knowledge.")
    )
    target_audience = models.JSONField(
        _("Who is this course for?"), # Stored as a list of strings
        default=list,
        blank=True
    )

    is_published = models.BooleanField(_("Published"), default=False, help_text=_("Whether the course is live and visible to users"))
    published_date = models.DateTimeField(_("Published Date"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # For average rating - can be calculated dynamically or stored and updated via signals/tasks
    average_rating = models.FloatField(_("Average Rating"), default=0.0)
    total_enrollments = models.PositiveIntegerField(_("Total Enrollments"), default=0) # Denormalized count

    class Meta:
        verbose_name = _("Course")
        verbose_name_plural = _("Courses")
        ordering = ['-created_at', 'title']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
            # Ensure uniqueness if multiple courses might have similar titles
            original_slug = self.slug
            queryset = Course.objects.filter(slug=original_slug).exists()
            counter = 1
            while queryset:
                self.slug = f"{original_slug}-{counter}"
                counter += 1
                queryset = Course.objects.filter(slug=self.slug).exists()
        if self.is_published and not self.published_date:
            self.published_date = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class Module(models.Model):
    """
    A module within a course, e.g., "Module 1: Introduction to Python".
    
    """
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
        unique_together = ('course', 'order') # Ensure order is unique per course

    def __str__(self):
        return f"{self.course.title} - Module {self.order}: {self.title}"

class Topic(models.Model):
    """
    A specific topic or lesson within a module, e.g., "Variables and Data Types".
    
    """
    CONTENT_TYPE_CHOICES = [
        ('text', _('Text Article')), # Rich text content 
        ('video', _('Video Lesson')), # Link to video content (URL)
        ('quiz', _('Quiz/Assessment')), # 
        ('assignment', _('Coding Assignment')), # Link to an assignment or embedded instructions
        ('external_resource', _('External Resource')), # Link to docs, articles, etc.
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='topics')
    title = models.CharField(_("Topic Title"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=270, unique=True, blank=True, help_text=_("URL-friendly identifier for the topic"))
    order = models.PositiveIntegerField(_("Topic Order"), default=0, help_text=_("Order of the topic within the module"))
    
    content_type = models.CharField(
        _("Content Type"),
        max_length=20,
        choices=CONTENT_TYPE_CHOICES,
        default='text'
    )
    # text_content_html: content from frontend editor for 'text' type 
    text_content_html = models.TextField(_("Text Content (HTML)"), blank=True, null=True, help_text=_("Used if content_type is 'text'"))
    video_url = models.URLField(_("Video URL"), blank=True, null=True, help_text=_("Used if content_type is 'video'"))
    # For 'quiz' and 'assignment', we might link to separate models or store JSON structure here.
    # quiz_data_json = models.JSONField(_("Quiz Data (JSON)"), blank=True, null=True, help_text=_("Structure for quiz questions, used if content_type is 'quiz'"))
    # assignment_details_html = models.TextField(_("Assignment Details (HTML)"), blank=True, null=True, help_text=_("Used if content_type is 'assignment'"))
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

    # For AI interactions:
    supports_ai_tutor = models.BooleanField(_("Supports AI Tutor"), default=True)
    supports_tts = models.BooleanField(_("Supports Text-to-Speech"), default=True) # For text-based content
    supports_ttv = models.BooleanField(_("Supports Text-to-Video"), default=False) # If this topic is suitable for AI video generation

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Topic")
        verbose_name_plural = _("Topics")
        ordering = ['module', 'order', 'title']
        unique_together = ('module', 'order') # Ensure order is unique per module

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            self.slug = f"{self.module.course.slug}-{self.module.id}-{base_slug}" # Ensure more global uniqueness for slugs
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.module.title} - Topic {self.order}: {self.title}"


class Quiz(models.Model):
    """
    Represents a quiz associated with a Topic.
    (Implied by content_type 'quiz')
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.OneToOneField(Topic, on_delete=models.CASCADE, related_name='quiz_details', limit_choices_to={'content_type': 'quiz'})
    title = models.CharField(_("Quiz Title"), max_length=255, blank=True) # Can inherit from topic title
    description = models.TextField(_("Quiz Description/Instructions"), blank=True, null=True)
    pass_mark_percentage = models.PositiveSmallIntegerField(
        _("Pass Mark Percentage"),
        default=70,
        help_text=_("Minimum percentage to pass the quiz")
    )
    time_limit_minutes = models.PositiveIntegerField(_("Time Limit (minutes)"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.title and self.topic:
            self.title = self.topic.title
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Quiz for: {self.topic.title}"

class Question(models.Model):
    """
    A question within a Quiz.
    """
    QUESTION_TYPE_CHOICES = [
        ('multiple_choice', _('Multiple Choice')),
        ('single_choice', _('Single Choice (Radio)')),
        ('true_false', _('True/False')),
        ('short_answer', _('Short Answer (Text Input)')),
        # ('fill_in_the_blanks', _('Fill in the Blanks')),
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
    explanation = models.TextField(_("Explanation for Answer"), blank=True, null=True, help_text=_("Shown after attempt"))
    points = models.PositiveSmallIntegerField(_("Points"), default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['quiz', 'order']

    def __str__(self):
        return f"Q{self.order}: {self.text[:50]}... ({self.quiz.title})"

class AnswerOption(models.Model):
    """
    An answer option for a multiple-choice or single-choice Question.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(_("Option Text"), max_length=500)
    is_correct = models.BooleanField(_("Is Correct Answer"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['question', 'id'] # Randomize order in serializer/view if needed for display

    def __str__(self):
        return f"{self.text} (Correct: {self.is_correct})"


# User Progress and Interaction Models

class UserCourseEnrollment(models.Model):
    """
    Tracks user enrollment in courses.
    (Conceptualized as UserCourseProgress in the guide, but enrollment is the first step)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(_("Completed At"), null=True, blank=True)
    # progress_percentage: calculated based on completed topics 
    # last_accessed_topic: ForeignKey to Topic, can be added 
    
    # Denormalized progress for quick lookups
    progress_percentage = models.PositiveSmallIntegerField(_("Progress Percentage"), default=0)
    last_accessed_topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = _("User Course Enrollment")
        verbose_name_plural = _("User Course Enrollments")
        unique_together = ('user', 'course') # User can only enroll once in a course
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.user.username} enrolled in {self.course.title}"

    def update_progress(self):
        """Calculates and updates the progress percentage for this enrollment."""
        total_topics = Topic.objects.filter(module__course=self.course).count()
        if total_topics == 0:
            self.progress_percentage = 100 if self.completed_at else 0 # No topics means instantly complete or 0
            self.save()
            return

        completed_topics_count = UserTopicAttempt.objects.filter(
            enrollment=self,
            is_completed=True
        ).count()
        
        self.progress_percentage = int((completed_topics_count / total_topics) * 100)
        
        if self.progress_percentage >= 100 and not self.completed_at:
            self.completed_at = timezone.now()
            # Potentially award certificate or XP here via a signal or task
            
        self.save()

class UserTopicAttempt(models.Model):
    """
    Tracks a user's attempt and status for a specific topic (lesson, quiz, etc.).
    
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(UserCourseEnrollment, on_delete=models.CASCADE, related_name='topic_attempts')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='user_attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='topic_attempts_direct') # Direct link for easier querying per user

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(_("Completed At"), null=True, blank=True)
    is_completed = models.BooleanField(_("Is Completed"), default=False)
    
    # For quizzes/assignments:
    score = models.FloatField(_("Score (0.0 to 1.0 or points)"), null=True, blank=True)
    passed = models.BooleanField(_("Passed"), null=True, blank=True) # Relevant for quizzes/assignments
    
    # answer_history_json: For quiz answers or assignment submissions 
    # Could store a list of dicts: {"question_id": "...", "answer_given": "...", "is_correct": ...}
    answer_history_json = models.JSONField(_("Answer History (JSON)"), null=True, blank=True)
    
    last_accessed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("User Topic Attempt")
        verbose_name_plural = _("User Topic Attempts")
        unique_together = ('enrollment', 'topic') # One attempt record per topic per enrollment
        ordering = ['enrollment', 'topic__module__order', 'topic__order']

    def save(self, *args, **kwargs):
        # Ensure user matches enrollment.user
        if self.enrollment and self.user != self.enrollment.user:
             raise ValueError("UserTopicAttempt user must match enrollment user.")
        
        super().save(*args, **kwargs)
        if self._state.adding or self.is_completed != self.__original_is_completed: # If new or completion status changed
            self.enrollment.update_progress() # Recalculate course progress

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_is_completed = self.is_completed


    def __str__(self):
        return f"{self.enrollment.user.username} - {self.topic.title} (Completed: {self.is_completed})"


class Review(models.Model):
    """
    User reviews and ratings for courses.
    
    """
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)] # 1 to 5 stars

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
        unique_together = ('course', 'user') # User can only review a course once
        ordering = ['-created_at']

    def __str__(self):
        return f"Review for {self.course.title} by {self.user.username} ({self.rating} stars)"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update average rating on the course (could be done via a signal for efficiency)
        self.course.average_rating = self.course.reviews.aggregate(models.Avg('rating'))['rating__avg'] or 0.0
        self.course.save(update_fields=['average_rating'])

from django.db.models.signals import post_delete
from django.dispatch import receiver

@receiver(post_delete, sender=Review)
def update_course_rating_on_delete(sender, instance, **kwargs):
    if instance.course:
        instance.course.average_rating = instance.course.reviews.aggregate(models.Avg('rating'))['rating__avg'] or 0.0
        instance.course.save(update_fields=['average_rating'])

# Import timezone utility
from django.utils import timezone
