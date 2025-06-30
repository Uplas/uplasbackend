
# apps/courses/serializers.py
from rest_framework import serializers
from .models import Category, Course, Module, Topic, Question, Choice

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']

class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choice
        fields = ['id', 'text', 'is_correct']

class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(many=True, read_only=True)
    class Meta:
        model = Question
        fields = ['id', 'text', 'question_type', 'choices']

class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ['id', 'title', 'slug', 'order', 'is_previewable']

class TopicDetailSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    class Meta:
        model = Topic
        fields = ['id', 'title', 'slug', 'order', 'content', 'estimated_duration_minutes', 'questions']

class ModuleSerializer(serializers.ModelSerializer):
    topics = TopicSerializer(many=True, read_only=True)
    class Meta:
        model = Module
        fields = ['id', 'title', 'order', 'topics']

class ModuleDetailSerializer(serializers.ModelSerializer):
    topics = TopicDetailSerializer(many=True, read_only=True)
    class Meta:
        model = Module
        fields = ['id', 'title', 'order', 'description', 'topics']

class CourseListSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()
    instructor = serializers.StringRelatedField()
    class Meta:
        model = Course
        fields = [
            'id', 'slug', 'title', 'short_description', 'thumbnail_url',
            'level', 'instructor', 'category', 'price', 'average_rating', 'total_enrollments'
        ]

class CourseDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    instructor = serializers.StringRelatedField()
    modules = ModuleSerializer(many=True, read_only=True)
    class Meta:
        model = Course
        fields = [
            'id', 'slug', 'title', 'long_description', 'modules',
            'instructor', 'category', 'price', 'level', 'language',
            'average_rating', 'total_reviews', 'total_enrollments', 'total_duration_minutes',
            'promo_video_url', 'supports_ai_tutor'
        ]