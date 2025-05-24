import uuid
from django.db import models
from django.conf import settings
from django.db.models import Avg, Count
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

# Choices
LANGUAGE_CHOICES = [
    ('en', _('English')),
    ('es', _('Spanish')),
    ('fr', _('French')),
    ('de', _('German')),
    # Add more languages as needed
]

LEVEL_CHOICES = [
    ('beginner', _('Beginner')),
    ('intermediate', _('Intermediate')),
    ('advanced', _('Advanced')),
]

QUESTION_TYPE_CHOICES = [
    ('multiple-choice', _('Multiple Choice')), # More than one correct answer possible
    ('single-choice', _('Single Choice')),   # Only one correct answer
    # ('true-false', _('True/False')),
    # ('fill-in-the-blank', _('Fill in the Blank')),
]

class Category(models.Model):
    """
    Model for course categories.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, verbose_name=_('Category Name'))
    slug = models.SlugField(max_length=120, unique=True, verbose_name=_('Slug'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))
    icon_url = models.URLField(blank=True, null=True, verbose_name=_('Icon URL'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')
        ordering = ['name']

    def __str__(self):
        return self.name

class Course(models.Model):
    """
    Model for courses.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, verbose_name=_('Course Title'))
    slug = models.SlugField(max_length=220, unique=True, verbose_name=_('Slug'))
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep course if instructor is deleted, but set instructor to NULL
        related_name='courses_taught',
        verbose_name=_('Instructor'),
        null=True,
        blank=True # Or PROTECT if instructor must always exist
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        related_name='courses',
        verbose_name=_('Category'),
        null=True,
        blank=True
    )
    short_description = models.TextField(verbose_name=_('Short Description'), help_text=_("A brief overview of the course."))
    long_description = models.TextField(blank=True, null=True, verbose_name=_('Long Description'), help_text=_("Detailed description of the course content and objectives."))
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='en', verbose_name=_('Language'))
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='beginner', verbose_name=_('Difficulty Level'))
    thumbnail_url = models.URLField(blank=True, null=True, verbose_name=_('Thumbnail URL'))
    promo_video_url = models.URLField(blank=True, null=True, verbose_name=_('Promotional Video URL'))

    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name=_('Price'))
    currency = models.CharField(max_length=3, default='USD', choices=settings.CURRENCY_CHOICES, verbose_name=_('Currency'))
    
    is_published = models.BooleanField(default=False, verbose_name=_('Is Published'))
    is_free = models.BooleanField(default=False, verbose_name=_('Is Free Course'))
    is_featured = models.BooleanField(default=False, verbose_name=_('Is Featured'))

    # Denormalized fields, updated by signals or tasks
    average_rating = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(5.0)], verbose_name=_('Average Rating'))
    total_reviews = models.PositiveIntegerField(default=0, verbose_name=_('Total Reviews'))
    total_enrollments = models.PositiveIntegerField(default=0, verbose_name=_('Total Enrollments'))
    total_duration_minutes = models.PositiveIntegerField(default=0, verbose_name=_('Estimated Total Duration (minutes)'), help_text=_("Sum of all topic durations in this course."))

    # AI Feature Flags
    supports_ai_tutor = models.BooleanField(default=False, verbose_name=_('Supports AI Tutor'))
    supports_tts = models.BooleanField(default=False, verbose_name=_('Supports Text-to-Speech'))
    supports_ttv = models.BooleanField(default=False, verbose_name=_('Supports Text-to-Video Instructors'))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))
    published_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Published At'))

    class Meta:
        verbose_name = _('Course')
        verbose_name_plural = _('Courses')
        ordering = ['-created_at', 'title'] # Default ordering

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.is_published and not self.published_at:
            self.published_at = models.functions.Now()
        elif not self.is_published:
            self.published_at = None # Reset if unpublished
        super().save(*args, **kwargs)

    def update_total_duration(self):
        """Recalculates and updates the total duration of the course based on its topics."""
        total_duration = Module.objects.filter(course=self).aggregate(
            total=models.Sum('topics__estimated_duration_minutes')
        )['total'] or 0
        self.total_duration_minutes = total_duration
        self.save(update_fields=['total_duration_minutes'])


class Module(models.Model):
    """
    Model for course modules (sections).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules', verbose_name=_('Course'))
    title = models.CharField(max_length=200, verbose_name=_('Module Title'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Module Description'))
    order = models.PositiveIntegerField(verbose_name=_('Module Order'), help_text=_("Order in which this module appears in the course."))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Module')
        verbose_name_plural = _('Modules')
        ordering = ['course', 'order', 'title'] # Order by course, then by explicit order, then title
        unique_together = [['course', 'order']] # Ensure order is unique within a course

    def __str__(self):
        return f"{self.course.title} - Module {self.order}: {self.title}"

class Topic(models.Model):
    """
    Model for individual topics or lessons within a module.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='topics', verbose_name=_('Module'))
    title = models.CharField(max_length=200, verbose_name=_('Topic Title'))
    slug = models.SlugField(max_length=220, unique=True, verbose_name=_('Slug')) # Ensure unique slug for direct linking
    
    # Flexible content structure. Example schema:
    # {
    #   "type": "text", // "video", "quiz", "external_resource", "code_interactive"
    #   "text_content": "Detailed explanation...", (Markdown or HTML)
    #   "video_url": "https://provider.com/video_id",
    #   "video_provider": "youtube", // "vimeo", "custom"
    #   "quiz_id": "uuid_of_quiz_associated_with_this_topic", // if type is 'quiz'
    #   "resource_url": "https://example.com/document.pdf",
    #   "code_language": "python",
    #   "initial_code": "print('Hello')",
    #   "solution_code": "print('Hello, World!')"
    # }
    content = models.JSONField(verbose_name=_('Topic Content'), help_text=_("JSON structured content for the topic."))
    
    estimated_duration_minutes = models.PositiveIntegerField(default=5, verbose_name=_('Estimated Duration (minutes)'))
    order = models.PositiveIntegerField(verbose_name=_('Topic Order'), help_text=_("Order in which this topic appears in the module."))
    
    # AI Feature Flags (can inherit from course or be specific)
    supports_ai_tutor = models.BooleanField(default=None, null=True, blank=True, verbose_name=_('Supports AI Tutor (Topic Specific)'))
    supports_tts = models.BooleanField(default=None, null=True, blank=True, verbose_name=_('Supports Text-to-Speech (Topic Specific)'))
    supports_ttv = models.BooleanField(default=None, null=True, blank=True, verbose_name=_('Supports Text-to-Video (Topic Specific)'))

    is_previewable = models.BooleanField(default=False, verbose_name=_('Is Previewable'), help_text=_("Can this topic be viewed by non-enrolled users?"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Topic')
        verbose_name_plural = _('Topics')
        ordering = ['module', 'order', 'title']
        unique_together = [['module', 'order']]

    def __str__(self):
        return f"{self.module.title} - Topic {self.order}: {self.title}"

    def get_supports_ai_tutor(self):
        """Returns AI tutor support status, inheriting from course if not set."""
        if self.supports_ai_tutor is not None:
            return self.supports_ai_tutor
        return self.module.course.supports_ai_tutor

    def get_supports_tts(self):
        """Returns TTS support status, inheriting from course if not set."""
        if self.supports_tts is not None:
            return self.supports_tts
        return self.module.course.supports_tts

    def get_supports_ttv(self):
        """Returns TTV support status, inheriting from course if not set."""
        if self.supports_ttv is not None:
            return self.supports_ttv
        return self.module.course.supports_ttv

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update course total duration when a topic's duration changes
        self.module.course.update_total_duration()

class Question(models.Model):
    """
    Model for quiz questions associated with a topic.
    A topic can have multiple questions forming a quiz.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='questions', verbose_name=_('Topic'))
    text = models.TextField(verbose_name=_('Question Text'))
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default='single-choice',
        verbose_name=_('Question Type')
    )
    order = models.PositiveIntegerField(verbose_name=_('Question Order'), help_text=_("Order of the question within the topic's quiz."))
    explanation = models.TextField(blank=True, null=True, verbose_name=_('Explanation'), help_text=_("Explanation for the correct answer, shown after attempt."))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Question')
        verbose_name_plural = _('Questions')
        ordering = ['topic', 'order']
        unique_together = [['topic', 'order']]

    def __str__(self):
        return f"Q{self.order}: {self.text[:50]}... ({self.topic.title})"

class Choice(models.Model):
    """
    Model for choices/options for a multiple-choice or single-choice question.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices', verbose_name=_('Question'))
    text = models.CharField(max_length=500, verbose_name=_('Choice Text'))
    is_correct = models.BooleanField(default=False, verbose_name=_('Is Correct Answer'))
    order = models.PositiveIntegerField(verbose_name=_('Choice Order'), default=0)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Choice')
        verbose_name_plural = _('Choices')
        ordering = ['question', 'order', 'text']
        # For single-choice, ensure only one is_correct per question (handled in form/serializer validation)
        # For multiple-choice, multiple can be is_correct

    def __str__(self):
        return f"{self.question.text[:30]}... - Choice: {self.text[:30]}..."


class Enrollment(models.Model):
    """
    Model to track user enrollments in courses.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments', verbose_name=_('User'))
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrolled_users', verbose_name=_('Course'))
    enrolled_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Enrolled At'))
    # Potentially add fields like 'completed_at', 'status' (e.g., 'active', 'completed', 'cancelled')
    # 'payment_id' could link to a Payment model if a separate payments app handles transactions.

    class Meta:
        verbose_name = _('Enrollment')
        verbose_name_plural = _('Enrollments')
        unique_together = [['user', 'course']] # User can only enroll once in a course
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.email} enrolled in {self.course.title}"

class CourseReview(models.Model):
    """
    Model for user reviews and ratings of courses.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews_given', verbose_name=_('User'))
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews', verbose_name=_('Course'))
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name=_('Rating (1-5)')
    )
    comment = models.TextField(blank=True, null=True, verbose_name=_('Comment'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created At'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated At'))

    class Meta:
        verbose_name = _('Course Review')
        verbose_name_plural = _('Course Reviews')
        unique_together = [['user', 'course']] # User can only review a course once
        ordering = ['-created_at']

    def __str__(self):
        return f"Review for {self.course.title} by {self.user.get_full_name() or self.user.email} - {self.rating} stars"

class CourseProgress(models.Model):
    """
    Tracks overall progress of a user in a course.
    This can be calculated based on TopicProgress.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_progresses', verbose_name=_('User'))
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='user_progresses', verbose_name=_('Course'))
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='progress_record', null=True, blank=True) # Link to specific enrollment
    completed_topics_count = models.PositiveIntegerField(default=0, verbose_name=_('Completed Topics Count'))
    total_topics_count = models.PositiveIntegerField(default=0, verbose_name=_('Total Topics Count in Course'))
    progress_percentage = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)], verbose_name=_('Progress Percentage'))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Course Completed At'))
    last_accessed_topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name='last_accessed_by_users', verbose_name=_('Last Accessed Topic'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Last Updated At'))


    class Meta:
        verbose_name = _('Course Progress')
        verbose_name_plural = _('Course Progresses')
        unique_together = [['user', 'course']]
        ordering = ['-updated_at']

    def __str__(self):
        return f"Progress for {self.user.email} in {self.course.title}: {self.progress_percentage:.2f}%"

    def update_progress(self):
        """Recalculates and updates the user's progress for this course."""
        if not self.enrollment: # Should ideally always have an enrollment
            self.total_topics_count = self.course.modules.aggregate(total_topics=Count('topics'))['total_topics'] or 0
        else:
            self.total_topics_count = Topic.objects.filter(module__course=self.course).count()

        self.completed_topics_count = TopicProgress.objects.filter(
            user=self.user,
            topic__module__course=self.course,
            is_completed=True
        ).count()

        if self.total_topics_count > 0:
            self.progress_percentage = (self.completed_topics_count / self.total_topics_count) * 100
        else:
            self.progress_percentage = 0

        if self.progress_percentage >= 100 and not self.completed_at:
            self.completed_at = models.functions.Now()
        elif self.progress_percentage < 100:
            self.completed_at = None # Reset if progress drops below 100%

        self.save()


class TopicProgress(models.Model):
    """
    Tracks user progress for individual topics.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='topic_progresses', verbose_name=_('User'))
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='user_progresses', verbose_name=_('Topic'))
    course_progress = models.ForeignKey(CourseProgress, on_delete=models.CASCADE, related_name='topic_progress_entries', null=True, blank=True)
    is_completed = models.BooleanField(default=False, verbose_name=_('Is Completed'))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Completed At'))
    # last_accessed_at = models.DateTimeField(auto_now=True) # Could be useful

    class Meta:
        verbose_name = _('Topic Progress')
        verbose_name_plural = _('Topic Progresses')
        unique_together = [['user', 'topic']]
        ordering = ['topic__module__order', 'topic__order']

    def __str__(self):
        return f"{self.user.email} progress on {self.topic.title} - {'Completed' if self.is_completed else 'In Progress'}"

    def save(self, *args, **kwargs):
        if self.is_completed and not self.completed_at:
            self.completed_at = models.functions.Now()
        elif not self.is_completed:
            self.completed_at = None

        # Ensure CourseProgress exists and link it
        if not self.course_progress:
            course_prog, _ = CourseProgress.objects.get_or_create(
                user=self.user,
                course=self.topic.module.course,
                defaults={'enrollment': Enrollment.objects.filter(user=self.user, course=self.topic.module.course).first()}
            )
            self.course_progress = course_prog
        
        super().save(*args, **kwargs)
        
        # After saving, update the overall course progress
        if self.course_progress:
            self.course_progress.update_progress()
            self.course_progress.last_accessed_topic = self.topic # Update last accessed topic
            self.course_progress.save(update_fields=['last_accessed_topic', 'updated_at'])


class QuizAttempt(models.Model):
    """
    Represents a user's attempt at a quiz for a specific topic.
    A topic's "quiz" is the collection of its Questions.
    This model stores the overall result of one attempt.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quiz_attempts')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='quiz_attempts')
    topic_progress = models.ForeignKey(TopicProgress, on_delete=models.CASCADE, related_name='quiz_results', null=True, blank=True)
    score = models.FloatField(verbose_name=_('Score (Percentage)'), validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    correct_answers = models.PositiveIntegerField(verbose_name=_('Correct Answers'))
    total_questions_in_topic = models.PositiveIntegerField(verbose_name=_('Total Questions in Topic Quiz'))
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Submitted At'))
    # For multiple attempts, you might add an attempt_number field.
    # For now, this assumes one main attempt record per topic completion or a "best score" record.

    class Meta:
        verbose_name = _('Quiz Attempt')
        verbose_name_plural = _('Quiz Attempts')
        # If only one attempt is allowed, or one "master" attempt is stored:
        unique_together = [['user', 'topic']] # Or remove if multiple attempts are stored here
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Quiz attempt for {self.topic.title} by {self.user.email} - Score: {self.score}%"

class UserTopicAttemptAnswer(models.Model):
    """
    Stores the specific answer(s) a user gave for a question in a quiz attempt.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz_attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='user_answers')
    selected_choices = models.ManyToManyField(Choice, blank=True, related_name='times_selected_in_answers') # For multiple/single choice
    # answer_text = models.TextField(blank=True, null=True) # For fill-in-the-blank or essay type
    is_correct = models.BooleanField(default=False, verbose_name=_('Was this answer correct for the question?'))

    class Meta:
        verbose_name = _('User Topic Quiz Answer')
        verbose_name_plural = _('User Topic Quiz Answers')
        # A user answers a question once per attempt
        unique_together = [['quiz_attempt', 'question']]

    def __str__(self):
        return f"Answer by {self.quiz_attempt.user.email} to Q: {self.question.text[:30]}..."


# --- Signals for denormalization ---
# Signals are often defined in models.py for simplicity in smaller apps,
# or in a dedicated signals.py file which is then imported in apps.py.

@receiver(post_save, sender=CourseReview)
@receiver(post_delete, sender=CourseReview)
def update_course_rating(sender, instance, **kwargs):
    """
    Updates the average rating and total reviews of a course
    when a review is saved or deleted.
    """
    course = instance.course
    reviews = CourseReview.objects.filter(course=course)
    course.average_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0.0
    course.total_reviews = reviews.count()
    course.save(update_fields=['average_rating', 'total_reviews'])

@receiver(post_save, sender=Enrollment)
@receiver(post_delete, sender=Enrollment)
def update_course_enrollments(sender, instance, **kwargs):
    """
    Updates the total enrollments of a course
    when an enrollment is created or deleted.
    """
    course = instance.course
    course.total_enrollments = Enrollment.objects.filter(course=course).count()
    course.save(update_fields=['total_enrollments'])

    # Also, ensure CourseProgress is created/deleted with enrollment
    if kwargs.get('created', False): # For post_save
        CourseProgress.objects.get_or_create(
            user=instance.user,
            course=instance.course,
            defaults={'enrollment': instance}
        )
    elif kwargs.get('signal') == post_delete: # For post_delete
        CourseProgress.objects.filter(user=instance.user, course=instance.course, enrollment=instance).delete()


@receiver(post_save, sender=Topic)
@receiver(post_delete, sender=Topic)
def update_course_total_duration_on_topic_change(sender, instance, **kwargs):
    """
    Updates the course's total duration when a topic is saved or deleted.
    """
    instance.module.course.update_total_duration()

# Note: TopicProgress signal already handles updating CourseProgress.
