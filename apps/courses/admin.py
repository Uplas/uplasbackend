# uplasbackend/apps/courses/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    Category, Course, Module, Topic, Question, Choice,
    Enrollment, CourseReview, CourseProgress, TopicProgress,
    QuizAttempt, UserTopicAttemptAnswer
)

class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1
    ordering = ('order',)

class TopicInline(admin.TabularInline):
    model = Topic
    extra = 1
    ordering = ('order',)
    prepopulated_fields = {'slug': ('title',)}

class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 2

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    inlines = [ChoiceInline]

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'id')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'instructor', 'category', 'price', 'is_published')
    list_filter = ('is_published', 'level', 'category', 'instructor')
    search_fields = ('title', 'short_description', 'instructor__email')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ModuleInline]

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    inlines = [TopicInline]

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'module', 'order', 'is_previewable')
    list_filter = ('module__course', 'is_previewable')
    search_fields = ('title', 'module__title')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [QuestionInline]

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'enrolled_at')
    search_fields = ('user__email', 'course__title')

@admin.register(CourseProgress)
class CourseProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'progress_percentage', 'completed_at')
    search_fields = ('user__email', 'course__title')

# Other models can be registered similarly if needed
admin.site.register(Question)
admin.site.register(Choice)
admin.site.register(CourseReview)
admin.site.register(TopicProgress)
admin.site.register(QuizAttempt)
admin.site.register(UserTopicAttemptAnswer)