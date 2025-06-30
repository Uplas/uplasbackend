# uplasbackend/apps/courses/models.py
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Avg, Count
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.core.models import BaseModel

# --- Choices ---
COURSE_LEVEL_CHOICES = [
    ('beginner', _('Beginner')),
    ('intermediate', _('Intermediate')),
    ('advanced', _('Advanced')),
]
QUESTION_TYPE_CHOICES = [
    ('single-choice', _('Single Choice')),
    ('multiple-choice', _('Multiple Choice')),
]

# --- Main Models ---
class Category(BaseModel):
    name = models.CharField(max_length=100, unique=True, verbose_name=_('Category Name'))
    slug = models.SlugField(max_length=120, unique=True, verbose_name=_('Slug'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))

    class Meta:
        verbose_name = _('Course Category')
        verbose_name_plural = _('Course Categories')
        ordering = ['name']
    def __str__(self): return self.name

class Course(BaseModel):
    instructor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='courses_taught', verbose_name=_('Instructor'))
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='courses', verbose_name=_('Category'))
    title = models.CharField(max_length=200, verbose_name=_('Title'))
    slug = models.SlugField(max_length=220, unique=True, verbose_name=_('Slug'))
    short_description = models.CharField(max_length=255, verbose_name=_('Short Description'))
    long_description = models.TextField(verbose_name=_('Long Description'))
    language = models.CharField(max_length=10, choices=settings.LANGUAGE_CHOICES, default='en', verbose_name=_('Language'))
    level = models.CharField(max_length=20, choices=COURSE_LEVEL_CHOICES, default='beginner', verbose_name=_('Difficulty Level'))
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name=_('Price'))
    currency = models.CharField(max_length=3, choices=settings.CURRENCY_CHOICES, default='USD', verbose_name=_('Currency'))
    is_free = models.BooleanField(default=False, verbose_name=_('Is Free'))
    is_published = models.BooleanField(default=False, verbose_name=_('Is Published'))
    is_featured = models.BooleanField(default=False, verbose_name=_('Is Featured'))
    thumbnail_url = models.URLField(blank=True, null=True, verbose_name=_('Thumbnail URL'))
    promo_video_url = models.URLField(blank=True, null=True, verbose_name=_('Promo Video URL'))
    published_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Published At'))
    supports_ai_tutor = models.BooleanField(default=False)
    supports_tts = models.BooleanField(default=False, verbose_name=_('Supports Text-to-Speech'))
    supports_ttv = models.BooleanField(default=False, verbose_name=_('Supports Text-to-Video'))
    average_rating = models.FloatField(default=0.0, editable=False)
    total_reviews = models.PositiveIntegerField(default=0, editable=False)
    total_enrollments = models.PositiveIntegerField(default=0, editable=False)
    total_duration_minutes = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        verbose_name = _('Course')
        verbose_name_plural = _('Courses')
        ordering = ['-created_at']
    def __str__(self): return self.title

class Module(BaseModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules', verbose_name=_('Course'))
    title = models.CharField(max_length=200, verbose_name=_('Title'))
    description = models.TextField(blank=True, null=True, verbose_name=_('Description'))
    order = models.PositiveIntegerField(verbose_name=_('Module Order'))

    class Meta:
        verbose_name = _('Module')
        verbose_name_plural = _('Modules')
        ordering = ['course', 'order']
        unique_together = [['course', 'order']]
    def __str__(self): return f"{self.course.title} - M{self.order}: {self.title}"

class Topic(BaseModel):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='topics', verbose_name=_('Module'))
    title = models.CharField(max_length=200, verbose_name=_('Topic Title'))
    slug = models.SlugField(max_length=220, unique=True, verbose_name=_('Slug'))
    content = models.JSONField(default=dict, help_text=_("e.g., {'type': 'video', 'url': '...', 'text_content': '...'}"))
    estimated_duration_minutes = models.PositiveIntegerField(default=5, verbose_name=_('Estimated Duration (Minutes)'))
    order = models.PositiveIntegerField(verbose_name=_('Topic Order'))
    is_previewable = models.BooleanField(default=False, help_text=_("Can non-enrolled users view this topic?"))
    supports_ai_tutor = models.BooleanField(null=True, blank=True)
    supports_tts = models.BooleanField(null=True, blank=True, verbose_name=_('Supports Text-to-Speech (Overrides Course)'))
    supports_ttv = models.BooleanField(null=True, blank=True, verbose_name=_('Supports Text-to-Video (Overrides Course)'))

    class Meta:
        verbose_name = _('Topic')
        verbose_name_plural = _('Topics')
        ordering = ['module', 'order']
        unique_together = [['module', 'order']]
    def __str__(self): return f"{self.module.title} - T{self.order}: {self.title}"

class Question(BaseModel):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='questions', verbose_name=_('Topic'))
    text = models.TextField(verbose_name=_('Question Text'))
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='single-choice')
    order = models.PositiveIntegerField(verbose_name=_('Question Order'))
    explanation = models.TextField(blank=True, null=True, help_text=_("Explanation for the correct answer."))

    class Meta:
        verbose_name = _('Quiz Question')
        verbose_name_plural = _('Quiz Questions')
        ordering = ['topic', 'order']
        unique_together = [['topic', 'order']]
    def __str__(self): return f"Q{self.order}: {self.text[:50]}... ({self.topic.title})"

class Choice(BaseModel):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices', verbose_name=_('Question'))
    text = models.CharField(max_length=500, verbose_name=_('Choice Text'))
    is_correct = models.BooleanField(default=False, verbose_name=_('Is Correct Answer'))
    order = models.PositiveIntegerField(verbose_name=_('Choice Order'))

    class Meta:
        verbose_name = _('Answer Choice')
        verbose_name_plural = _('Answer Choices')
        ordering = ['question', 'order']
        unique_together = [['question', 'order']]
    def __str__(self): return f"{self.question.text[:30]}... - Choice: {self.text[:30]}..."

class Enrollment(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['user', 'course']]
    def __str__(self): return f"{self.user.full_name} enrolled in {self.course.title}"

class CourseReview(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = [['user', 'course']]
    def __str__(self): return f"Review for {self.course.title} by {self.user.full_name} - {self.rating} stars"

class CourseProgress(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='progress')
    completed_topics_count = models.PositiveIntegerField(default=0)
    total_topics_count = models.PositiveIntegerField(default=0)
    progress_percentage = models.FloatField(default=0.0)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed_topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)

class TopicProgress(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    course_progress = models.ForeignKey(CourseProgress, on_delete=models.CASCADE, related_name='topic_progresses')
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [['user', 'topic']]

class QuizAttempt(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    topic_progress = models.ForeignKey(TopicProgress, on_delete=models.CASCADE, null=True)
    score = models.FloatField(default=0.0)
    correct_answers = models.PositiveIntegerField(default=0)
    total_questions_in_topic = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

class UserTopicAttemptAnswer(BaseModel):
    quiz_attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choices = models.ManyToManyField(Choice)
    is_correct = models.BooleanField(default=False)