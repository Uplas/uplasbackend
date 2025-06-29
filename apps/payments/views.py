# payments/views.py
import hashlib
import hmac
import json
from datetime import date, timedelta
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from users.models import User
from .models import Plan, Subscription, Payment

@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def paystack_webhook(request):
    """
    Handles Paystack webhook events.
    """
    paystack_secret_key = settings.PAYSTACK_SECRET_KEY
    if not paystack_secret_key:
        return HttpResponse(status=500, content='Paystack secret key not configured.')

    # Verify the event by checking the signature
    signature = request.headers.get('x-paystack-signature')
    if not signature:
        return HttpResponse(status=400, content='Missing signature header')

    computed_signature = hmac.new(
        paystack_secret_key.encode('utf-8'),
        request.body,
        hashlib.sha512
    ).hexdigest()

    if signature != computed_signature:
        return HttpResponse(status=400, content='Invalid signature')

    # Process the event
    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400, content='Invalid JSON payload')

    event_type = event.get('event')

    if event_type == 'charge.success':
        data = event.get('data')
        email = data['customer']['email']
        amount = data['amount'] / 100  # Amount is in kobo
        reference = data['reference']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return HttpResponse(status=404, content=f'User with email {email} not found.')

        # Find a plan that matches the amount paid
        try:
            plan = Plan.objects.get(price=amount)
        except Plan.DoesNotExist:
             return HttpResponse(status=404, content=f'No plan found for amount {amount}.')

        # Create or update subscription
        subscription, created = Subscription.objects.update_or_create(
            user=user,
            defaults={
                'plan': plan,
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=plan.duration_days),
                'is_active': True,
            }
        )
        
        # Log the payment
        Payment.objects.create(
            user=user,
            amount=amount,
            reference=reference,
            status='success'
        )

        return HttpResponse(status=200)

    # You can handle other event types here (e.g., charge.failed)

    return HttpResponse(status=200)
