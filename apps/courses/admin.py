from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    Category, Course, Module, Topic, Question, Choice,
    Enrollment, CourseReview, CourseProgress, TopicProgress,
    QuizAttempt, UserTopicAttemptAnswer
)

# --- Inlines for easier management of related objects ---

class ModuleInline(admin.TabularInline):
    """
    Inline for managing Modules directly within the Course admin page.
    """
    model = Module
    extra = 1 # Number of empty forms to display
    ordering = ('order',)
    fields = ('title', 'order', 'description')
    show_change_link = True

class TopicInline(admin.TabularInline):
    """
    Inline for managing Topics directly within the Module admin page.
    """
    model = Topic
    extra = 1
    ordering = ('order',)
    fields = ('title', 'slug', 'order', 'estimated_duration_minutes', 'is_previewable', 'content') # Content might be large for inline
    prepopulated_fields = {'slug': ('title',)}
    show_change_link = True
    # Consider using a simplified form for inline Topic if 'content' JSON is too complex here

class ChoiceInline(admin.TabularInline):
    """
    Inline for managing Choices directly within the Question admin page.
    """
    model = Choice
    extra = 2
    ordering = ('order',)
    fields = ('text', 'is_correct', 'order')

class QuestionInline(admin.TabularInline):
    """
    Inline for managing Questions directly within the Topic admin page.
    """
    model = Question
    extra = 1
    ordering = ('order',)
    fields = ('text', 'question_type', 'order', 'explanation')
    show_change_link = True


# --- ModelAdmin configurations ---

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Category model.
    """
    list_display = ('name', 'slug', 'course_count', 'created_at')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'created_at', 'updated_at')

    def course_count(self, obj):
        return obj.courses.count()
    course_count.short_description = _('Number of Courses')

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Course model.
    """
    list_display = (
        'title', 'instructor_email', 'category_name', 'price', 'currency', 'is_published',
        'is_free', 'average_rating', 'total_enrollments', 'created_at'
    )
    list_filter = ('is_published', 'is_free', 'level', 'language', 'category', 'instructor')
    search_fields = ('title', 'slug', 'short_description', 'instructor__email', 'instructor__username', 'category__name')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = (
        'id', 'average_rating', 'total_reviews', 'total_enrollments',
        'created_at', 'updated_at', 'published_at', 'total_duration_minutes'
    )
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'instructor', 'category')}),
        (_('Course Details'), {'fields': (
            'short_description', 'long_description', 'language', 'level',
            'thumbnail_url', 'promo_video_url'
        )}),
        (_('Pricing & Status'), {'fields': (
            'price', 'currency', 'is_free', 'is_published', 'is_featured', 'published_at'
        )}),
        (_('AI Features'), {'fields': ('supports_ai_tutor', 'supports_tts', 'supports_ttv')}),
        (_('Metrics (Read-Only)'), {'fields': (
            'average_rating', 'total_reviews', 'total_enrollments', 'total_duration_minutes'
        )}),
        (_('Important Dates (Read-Only)'), {'fields': ('created_at', 'updated_at')}),
    )
    inlines = [ModuleInline]
    actions = ['publish_courses', 'unpublish_courses']

    def instructor_email(self, obj):
        return obj.instructor.email if obj.instructor else '-'
    instructor_email.short_description = _('Instructor Email')
    instructor_email.admin_order_field = 'instructor__email'

    def category_name(self, obj):
        return obj.category.name if obj.category else '-'
    category_name.short_description = _('Category')
    category_name.admin_order_field = 'category__name'

    def publish_courses(self, request, queryset):
        queryset.update(is_published=True, published_at=models.functions.Now())
    publish_courses.short_description = _("Publish selected courses")

    def unpublish_courses(self, request, queryset):
        queryset.update(is_published=False, published_at=None)
    unpublish_courses.short_description = _("Unpublish selected courses")

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Module model.
    """
    list_display = ('title', 'course_title', 'order', 'topic_count', 'created_at')
    list_filter = ('course__category', 'course__instructor')
    search_fields = ('title', 'description', 'course__title')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fields = ('course', 'title', 'description', 'order') # Control field order
    inlines = [TopicInline]
    list_select_related = ('course',) # Optimize query

    def course_title(self, obj):
        return obj.course.title
    course_title.short_description = _('Course')
    course_title.admin_order_field = 'course__title'

    def topic_count(self, obj):
        return obj.topics.count()
    topic_count.short_description = _('Number of Topics')

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Topic model.
    """
    list_display = (
        'title', 'module_title_with_course', 'order',
        'estimated_duration_minutes', 'is_previewable', 'question_count'
    )
    list_filter = ('module__course__category', 'module__course__instructor', 'is_previewable')
    search_fields = ('title', 'slug', 'module__title', 'module__course__title')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('module', 'title', 'slug', 'order')}),
        (_('Content & Settings'), {'fields': (
            'content', 'estimated_duration_minutes', 'is_previewable'
        )}),
        (_('AI Features (Overrides Course Setting)'), {'fields': (
            'supports_ai_tutor', 'supports_tts', 'supports_ttv'
        )}),
    )
    inlines = [QuestionInline]
    list_select_related = ('module', 'module__course') # Optimize query

    def module_title_with_course(self, obj):
        return f"{obj.module.course.title} - {obj.module.title}"
    module_title_with_course.short_description = _('Module (Course)')
    module_title_with_course.admin_order_field = 'module__title' # or module__course__title

    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = _('Number of Questions')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Question model.
    """
    list_display = ('text_summary', 'topic_title_summary', 'question_type', 'order', 'choice_count')
    list_filter = ('question_type', 'topic__module__course__category', 'topic__module__course')
    search_fields = ('text', 'topic__title', 'topic__module__title')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fields = ('topic', 'text', 'question_type', 'order', 'explanation')
    inlines = [ChoiceInline]
    list_select_related = ('topic', 'topic__module') # Optimize query

    def text_summary(self, obj):
        return obj.text[:75] + '...' if len(obj.text) > 75 else obj.text
    text_summary.short_description = _('Question Text')

    def topic_title_summary(self, obj):
        return obj.topic.title[:50] + '...' if len(obj.topic.title) > 50 else obj.topic.title
    topic_title_summary.short_description = _('Topic')
    topic_title_summary.admin_order_field = 'topic__title'

    def choice_count(self, obj):
        return obj.choices.count()
    choice_count.short_description = _('Number of Choices')

@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Choice model.
    Usually managed inline with Question, but can be accessed directly.
    """
    list_display = ('text_summary', 'question_summary', 'is_correct', 'order')
    list_filter = ('is_correct', 'question__topic__module__course')
    search_fields = ('text', 'question__text')
    readonly_fields = ('id', 'created_at', 'updated_at')
    list_select_related = ('question', 'question__topic') # Optimize query

    def text_summary(self, obj):
        return obj.text[:75] + '...' if len(obj.text) > 75 else obj.text
    text_summary.short_description = _('Choice Text')

    def question_summary(self, obj):
        return obj.question.text[:50] + '...' if len(obj.question.text) > 50 else obj.question.text
    question_summary.short_description = _('Question')
    question_summary.admin_order_field = 'question__text'


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Enrollment model.
    """
    list_display = ('user_email', 'course_title', 'enrolled_at')
    list_filter = ('course__category', 'course__instructor', 'enrolled_at')
    search_fields = ('user__email', 'user__username', 'course__title')
    readonly_fields = ('id', 'enrolled_at', 'user', 'course') # Usually created via application logic
    list_select_related = ('user', 'course') # Optimize query

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = _('User Email')
    user_email.admin_order_field = 'user__email'

    def course_title(self, obj):
        return obj.course.title
    course_title.short_description = _('Course Title')
    course_title.admin_order_field = 'course__title'

@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    """
    Admin configuration for the CourseReview model.
    """
    list_display = ('course_title', 'user_email', 'rating', 'created_at_formatted')
    list_filter = ('rating', 'course__category', 'course__instructor', 'created_at')
    search_fields = ('comment', 'user__email', 'course__title')
    readonly_fields = ('id', 'created_at', 'updated_at', 'user', 'course') # Usually created via application logic
    list_select_related = ('user', 'course') # Optimize query
    fields = ('user', 'course', 'rating', 'comment', 'created_at', 'updated_at')

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = _('User Email')

    def course_title(self, obj):
        return obj.course.title
    course_title.short_description = _('Course Title')

    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%Y-%m-%d %H:%M")
    created_at_formatted.short_description = _('Created At')
    created_at_formatted.admin_order_field = 'created_at'


class UserTopicAttemptAnswerInline(admin.TabularInline):
    model = UserTopicAttemptAnswer
    extra = 0
    readonly_fields = ('question', 'selected_choices_display', 'is_correct')
    fields = ('question', 'selected_choices_display', 'is_correct')
    can_delete = False

    def selected_choices_display(self, obj):
        return ", ".join([choice.text for choice in obj.selected_choices.all()])
    selected_choices_display.short_description = _('Selected Choices')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    """
    Admin configuration for the QuizAttempt model.
    """
    list_display = ('user_email', 'topic_title', 'score_percentage', 'submitted_at_formatted')
    list_filter = ('topic__module__course', 'submitted_at')
    search_fields = ('user__email', 'topic__title')
    readonly_fields = ('id', 'user', 'topic', 'topic_progress', 'score', 'correct_answers', 'total_questions_in_topic', 'submitted_at')
    list_select_related = ('user', 'topic', 'topic__module')
    inlines = [UserTopicAttemptAnswerInline]
    fieldsets = (
        (None, {'fields': ('user', 'topic', 'topic_progress')}),
        (_('Quiz Results'), {'fields': ('score', 'correct_answers', 'total_questions_in_topic')}),
        (_('Submission Time'), {'fields': ('submitted_at',)}),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = _('User Email')

    def topic_title(self, obj):
        return obj.topic.title
    topic_title.short_description = _('Topic')

    def score_percentage(self, obj):
        return f"{obj.score:.2f}%"
    score_percentage.short_description = _('Score')

    def submitted_at_formatted(self, obj):
        return obj.submitted_at.strftime("%Y-%m-%d %H:%M")
    submitted_at_formatted.short_description = _('Submitted At')
    submitted_at_formatted.admin_order_field = 'submitted_at'


@admin.register(CourseProgress)
class CourseProgressAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'course_title', 'progress_percentage_display', 'completed_at', 'updated_at')
    list_filter = ('course__category', 'course__instructor', 'completed_at')
    search_fields = ('user__email', 'course__title')
    readonly_fields = ('id', 'user', 'course', 'enrollment', 'completed_topics_count', 'total_topics_count', 'progress_percentage', 'completed_at', 'last_accessed_topic', 'updated_at')
    list_select_related = ('user', 'course', 'last_accessed_topic')

    def user_email(self, obj): return obj.user.email
    def course_title(self, obj): return obj.course.title
    def progress_percentage_display(self, obj): return f"{obj.progress_percentage:.2f}%"
    progress_percentage_display.short_description = _('Progress')


@admin.register(TopicProgress)
class TopicProgressAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'topic_title_with_module', 'is_completed', 'completed_at')
    list_filter = ('is_completed', 'topic__module__course__category', 'completed_at')
    search_fields = ('user__email', 'topic__title')
    readonly_fields = ('id', 'user', 'topic', 'course_progress', 'is_completed', 'completed_at')
    list_select_related = ('user', 'topic', 'topic__module', 'course_progress', 'course_progress__course')

    def user_email(self, obj): return obj.user.email
    def topic_title_with_module(self, obj): return f"{obj.topic.module.title} - {obj.topic.title}"
    topic_title_with_module.short_description = _('Topic')
