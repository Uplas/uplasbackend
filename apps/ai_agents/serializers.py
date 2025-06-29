# apps/ai_agents/serializers.py
from rest_framework import serializers
from .models import AIAgent

class AIAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIAgent
        fields = ['id', 'name', 'persona', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
