# courses/serializers.py
from rest_framework import serializers
from .models import Category, Course, Module, Lesson, TeamMember
from payments.models import Subscription

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['name', 'slug']

class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ['id', 'title']

class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)
    is_unlocked = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = ['id', 'title', 'order', 'is_unlocked', 'lessons']

    def get_is_unlocked(self, obj):
        # For simplicity, we'll say the first module is always unlocked.
        # In a real app, you'd check user progress or subscription status.
        return obj.order == 1

class CourseListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    is_enrolled = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id', 'slug', 'title', 'short_description', 'thumbnail_url',
            'difficulty', 'duration_hours', 'is_premium', 'is_enrolled', 'category'
        ]

    def get_is_enrolled(self, obj):
        user = self.context['request'].user
        if user.is_authenticated:
            return obj.enrolled_users.filter(id=user.id).exists()
        return False

class CourseDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    modules = ModuleSerializer(many=True, read_only=True)
    is_enrolled = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id', 'slug', 'title', 'short_description', 'long_description',
            'thumbnail_url', 'instructor_name', 'duration_hours', 'difficulty',
            'price', 'is_premium', 'is_enrolled', 'category', 'modules'
        ]

    def get_is_enrolled(self, obj):
        user = self.context['request'].user
        if user.is_authenticated:
            return obj.enrolled_users.filter(id=user.id).exists()
        return False

class LessonContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ['content']

class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = '__all__'
