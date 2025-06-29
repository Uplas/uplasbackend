# courses/views.py
from rest_framework import generics, permissions, filters
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Course, Lesson, TeamMember
from .serializers import CourseListSerializer, CourseDetailSerializer, LessonContentSerializer, TeamMemberSerializer
from payments.models import Subscription

class CourseListView(generics.ListAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['category__slug', 'difficulty']
    search_fields = ['title', 'short_description', 'long_description']

class CourseDetailView(generics.RetrieveAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

class LessonContentView(generics.RetrieveAPIView):
    queryset = Lesson.objects.all()
    serializer_class = LessonContentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        # Check if the user has an active subscription
        has_active_subscription = Subscription.objects.filter(
            user=request.user, 
            is_active=True
        ).exists()

        if not has_active_subscription:
            return Response({"detail": "You do not have an active subscription to view this content."}, status=403)
        
        return super().retrieve(request, *args, **kwargs)

class TeamMemberListView(generics.ListAPIView):
    queryset = TeamMember.objects.all()
    serializer_class = TeamMemberSerializer
    permission_classes = [permissions.AllowAny]
