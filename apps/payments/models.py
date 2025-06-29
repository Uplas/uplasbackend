# payments/models.py
from django.db import models
from django.conf import settings

class Plan(models.Model):
    name = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.name} - ${self.price}"

class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.email}'s Subscription to {self.plan.name}"

class Payment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=50, choices=[('success', 'Success'), ('failed', 'Failed')])
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment of ${self.amount} by {self.user.email} - {self.status}"
