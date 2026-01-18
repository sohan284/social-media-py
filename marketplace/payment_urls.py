# payment_urls.py
from django.urls import path
from .payment_webhooks import stripe_webhook

urlpatterns = [
    path('stripe-webhook/', stripe_webhook, name='stripe-webhook'),
]

