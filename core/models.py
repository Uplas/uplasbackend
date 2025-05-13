from django.db import models
from django.contrib.auth.models import User

class Link(models.Model):
    title = models.CharField(max_length=255)
    url = models.URLField()
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
