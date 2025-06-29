# apps/ai_agents/models.py
import uuid
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel

class AIAgent(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_agents')
    name = models.CharField(max_length=255)
    persona = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
