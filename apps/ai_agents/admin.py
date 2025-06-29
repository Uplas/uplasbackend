# apps/ai_agents/admin.py
from django.contrib import admin
from .models import AIAgent

@admin.register(AIAgent)
class AIAgentAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_active', 'created_at')
    list_filter = ('is_active', 'user')
    search_fields = ('name', 'persona')
