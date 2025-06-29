# payments/urls.py
from django.urls import path
from .views import paystack_webhook

urlpatterns = [
    path('paystack/webhook/', paystack_webhook, name='paystack_webhook'),
]
