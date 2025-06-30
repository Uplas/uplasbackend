
# apps/courses/views.py
from rest_framework import viewsets, generics, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Category, Course, Module, Topic
from .serializers import CategorySerializer, CourseListSerializer, CourseDetailSerializer, ModuleDetailSerializer, TopicDetailSerializer
from apps.payments.models import UserSubscription # CORRECTED IMPORT
from .permissions import IsInstructorOrReadOnly, IsEnrolled

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.filter(is_published=True)
    permission_classes = [IsInstructorOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category__slug', 'level']
    search_fields = ['title', 'short_description', 'long_description']
    ordering_fields = ['title', 'price', 'created_at', 'average_rating']
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return CourseListSerializer
        return CourseDetailSerializer

    def perform_create(self, serializer):
        serializer.save(instructor=self.request.user)

class ModuleViewSet(viewsets.ModelViewSet):
    serializer_class = ModuleDetailSerializer
    permission_classes = [IsInstructorOrReadOnly]

    def get_queryset(self):
        course_slug = self.kwargs.get('course_slug')
        return Module.objects.filter(course__slug=course_slug).order_by('order')

    def perform_create(self, serializer):
        course = Course.objects.get(slug=self.kwargs.get('course_slug'))
        serializer.save(course=course)

class TopicViewSet(viewsets.ModelViewSet):
    serializer_class = TopicDetailSerializer
    permission_classes = [IsEnrolled] # Users must be enrolled to view topics
    lookup_field = 'slug'

    def get_queryset(self):
        module_id = self.kwargs.get('module_pk')
        return Topic.objects.filter(module_id=module_id).order_by('order')

    def perform_create(self, serializer):
        module = Module.objects.get(pk=self.kwargs.get('module_pk'))
        serializer.save(module=module)