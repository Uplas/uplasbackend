# apps/ai_agents/views.py
from rest_framework import viewsets
from .models import AIAgent
from .serializers import AIAgentSerializer
from rest_framework.permissions import IsAuthenticated

class AIAgentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows AI agents to be viewed or edited.
    """
    serializer_class = AIAgentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        This view should return a list of all the AI agents
        for the currently authenticated user.
        """
        return AIAgent.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
