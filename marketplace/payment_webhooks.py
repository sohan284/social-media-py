# payment_webhooks.py
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    stripe = None
    STRIPE_AVAILABLE = False
    
import logging
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
from .models import SubscriptionPlan, UserSubscription, Payment, PostCredit
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)

if STRIPE_AVAILABLE:
    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)
else:
    webhook_secret = None


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Handle Stripe webhook events"""
    if not STRIPE_AVAILABLE:
        logger.error("Stripe is not available")
        return HttpResponse("Stripe not available", status=503)
        
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {str(e)}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {str(e)}")
        return HttpResponse(status=400)
    
    # Handle the event
    event_type = event['type']
    data = event['data']['object']
    
    logger.info(f"Received Stripe webhook: {event_type}")
    
    try:
        if event_type == 'checkout.session.completed':
            handle_checkout_completed(data)
        elif event_type == 'customer.subscription.created':
            handle_subscription_created(data)
        elif event_type == 'customer.subscription.updated':
            handle_subscription_updated(data)
        elif event_type == 'customer.subscription.deleted':
            handle_subscription_deleted(data)
        elif event_type == 'invoice.payment_succeeded':
            handle_invoice_payment_succeeded(data)
        elif event_type == 'invoice.payment_failed':
            handle_invoice_payment_failed(data)
        else:
            logger.info(f"Unhandled event type: {event_type}")
    except Exception as e:
        logger.error(f"Error handling webhook {event_type}: {str(e)}")
        return HttpResponse(status=500)
    
    return HttpResponse(status=200)


def handle_checkout_completed(session):
    """Handle successful checkout session"""
    metadata = session.get('metadata', {})
    user_id = metadata.get('user_id')
    payment_type = metadata.get('type')
    
    if not user_id:
        logger.error("No user_id in checkout session metadata")
        return
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return
    
    if payment_type == 'subscription':
        # Get subscription details from session
        subscription_id = session.get('subscription')
        plan_id = metadata.get('plan_id')
        
        # Get amount from session
        amount_total = session.get('amount_total', 0) / 100  # Convert from cents
        
        # If amount is 0, try to retrieve the checkout session with expanded line items
        if amount_total == 0:
            try:
                session_id = session.get('id')
                expanded_session = stripe.checkout.Session.retrieve(
                    session_id,
                    expand=['line_items']
                )
                if expanded_session.get('line_items') and expanded_session['line_items'].get('data'):
                    line_item = expanded_session['line_items']['data'][0]
                    amount_total = line_item.get('amount_total', 0) / 100
            except Exception as e:
                logger.error(f"Error retrieving checkout session details: {str(e)}")
        
        # If still no amount and we have subscription_id, try to retrieve from subscription
        if amount_total == 0 and subscription_id:
            try:
                stripe_subscription = stripe.Subscription.retrieve(subscription_id)
                if stripe_subscription.get('items', {}).get('data'):
                    amount_total = stripe_subscription['items']['data'][0]['price']['unit_amount'] / 100
            except Exception as e:
                logger.error(f"Error retrieving subscription amount: {str(e)}")
        
        # Get or create user subscription
        user_subscription, _ = UserSubscription.objects.get_or_create(
            user=user,
            defaults={'plan_id': plan_id, 'status': 'active', 'stripe_subscription_id': subscription_id}
        )
        
        # Get plan for description
        plan = None
        if plan_id:
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id)
            except SubscriptionPlan.DoesNotExist:
                pass
        
        # Check if payment already exists to avoid duplicates
        existing_payment = Payment.objects.filter(
            user=user,
            subscription=user_subscription,
            payment_type='subscription',
            metadata__subscription_id=subscription_id
        ).first()
        
        if not existing_payment:
            # Create payment record
            Payment.objects.create(
                user=user,
                subscription=user_subscription,
                payment_type='subscription',
                amount=amount_total,
                currency='usd',
                status='succeeded',
                stripe_payment_intent_id=session.get('payment_intent'),
                stripe_charge_id=session.get('payment_intent'),  # For subscriptions, payment_intent is available
                description=f'Subscription to {plan.display_name if plan else "Plan"}' if plan else 'Subscription payment',
                metadata={
                    'subscription_id': subscription_id,
                    'session_id': session.get('id'),
                    **metadata
                }
            )
            logger.info(f"Subscription payment record created for user {user_id}, amount: ${amount_total}")
        else:
            logger.info(f"Payment record already exists for subscription {subscription_id}")
    elif payment_type == 'one_time_post':
        # Create payment record and credit
        amount = session.get('amount_total', 0) / 100  # Convert from cents
        post_count = int(metadata.get('post_count', 1))
        
        payment = Payment.objects.create(
            user=user,
            payment_type='one_time',
            amount=amount,
            currency='usd',
            status='succeeded',
            stripe_payment_intent_id=session.get('payment_intent'),
            description=f'One-time payment for {post_count} promotion post(s)',
            metadata=metadata
        )
        
        # Create post credit
        PostCredit.objects.create(
            user=user,
            amount=post_count,
            payment=payment,
            expires_at=None  # Credits don't expire
        )
        
        logger.info(f"Created {post_count} post credit(s) for user {user_id}")


def handle_subscription_created(subscription):
    """Handle new subscription creation"""
    customer_id = subscription.get('customer')
    subscription_id = subscription.get('id')
    price_id = subscription.get('items', {}).get('data', [{}])[0].get('price', {}).get('id')
    
    if not price_id:
        logger.error("No price_id in subscription")
        return
    
    try:
        plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)
    except SubscriptionPlan.DoesNotExist:
        logger.error(f"Plan with price_id {price_id} not found")
        return
    
    # Find user by customer_id
    try:
        user_subscription = UserSubscription.objects.get(stripe_customer_id=customer_id)
        user = user_subscription.user
    except UserSubscription.DoesNotExist:
        # Try to get from metadata
        metadata = subscription.get('metadata', {})
        user_id = metadata.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                user_subscription, _ = UserSubscription.objects.get_or_create(
                    user=user,
                    defaults={'stripe_customer_id': customer_id}
                )
            except User.DoesNotExist:
                logger.error(f"User {user_id} not found")
                return
        else:
            logger.error("No user found for subscription")
            return
    
    # Check if plan is changing - if so, reset post count
    plan_changed = user_subscription.plan != plan
    if plan_changed:
        logger.info(f"Plan changed from {user_subscription.plan.display_name if user_subscription.plan else 'None'} to {plan.display_name}. Resetting post count.")
        user_subscription.posts_used_this_month = 0
        user_subscription.last_reset_date = timezone.now()
    
    # Update subscription
    user_subscription.plan = plan
    user_subscription.status = 'active'
    user_subscription.stripe_subscription_id = subscription_id
    user_subscription.current_period_start = timezone.datetime.fromtimestamp(
        subscription.get('current_period_start'), tz=timezone.utc
    )
    user_subscription.current_period_end = timezone.datetime.fromtimestamp(
        subscription.get('current_period_end'), tz=timezone.utc
    )
    user_subscription.save()
    
    # Check if payment record already exists (created in checkout.session.completed)
    # If not, create it here as fallback
    existing_payment = Payment.objects.filter(
        subscription=user_subscription,
        payment_type='subscription',
        stripe_payment_intent_id__isnull=False
    ).first()
    
    if not existing_payment:
        # Create payment record as fallback (shouldn't happen if checkout.session.completed fired)
        amount = subscription.get('items', {}).get('data', [{}])[0].get('price', {}).get('unit_amount', 0) / 100
        Payment.objects.create(
            user=user,
            subscription=user_subscription,
            payment_type='subscription',
            amount=amount,
            currency='usd',
            status='succeeded',
            description=f'Subscription to {plan.display_name}',
            metadata={'subscription_id': subscription_id, 'created_from': 'subscription.created_event'}
        )
        logger.info(f"Payment record created from subscription.created event for user {user.id}")
    
    logger.info(f"Subscription created for user {user.id}")


def handle_subscription_updated(subscription):
    """Handle subscription updates"""
    subscription_id = subscription.get('id')
    
    try:
        user_subscription = UserSubscription.objects.get(stripe_subscription_id=subscription_id)
    except UserSubscription.DoesNotExist:
        logger.error(f"Subscription {subscription_id} not found")
        return
    
    user_subscription.status = subscription.get('status', 'active')
    if subscription.get('current_period_start'):
        user_subscription.current_period_start = datetime.fromtimestamp(
            subscription.get('current_period_start'), tz=timezone.utc
        )
    if subscription.get('current_period_end'):
        user_subscription.current_period_end = datetime.fromtimestamp(
            subscription.get('current_period_end'), tz=timezone.utc
        )
    user_subscription.cancel_at_period_end = subscription.get('cancel_at_period_end', False)
    user_subscription.save()
    
    logger.info(f"Subscription {subscription_id} updated")


def handle_subscription_deleted(subscription):
    """Handle subscription cancellation"""
    subscription_id = subscription.get('id')
    
    try:
        user_subscription = UserSubscription.objects.get(stripe_subscription_id=subscription_id)
        user_subscription.status = 'canceled'
        user_subscription.plan = None
        user_subscription.save()
        logger.info(f"Subscription {subscription_id} canceled")
    except UserSubscription.DoesNotExist:
        logger.error(f"Subscription {subscription_id} not found")


def handle_invoice_payment_succeeded(invoice):
    """Handle successful invoice payment"""
    subscription_id = invoice.get('subscription')
    if subscription_id:
        # Subscription payment - update period dates
        try:
            user_subscription = UserSubscription.objects.get(stripe_subscription_id=subscription_id)
            from datetime import datetime
            user_subscription.current_period_start = datetime.fromtimestamp(
                invoice.get('period_start'), tz=timezone.utc
            )
            user_subscription.current_period_end = datetime.fromtimestamp(
                invoice.get('period_end'), tz=timezone.utc
            )
            user_subscription.status = 'active'
            user_subscription.save()
            
            # Reset monthly usage on new billing period
            user_subscription.reset_monthly_usage()
            
            # Create payment record for all successful invoice payments
            # Check if this is the initial payment (billing_reason == 'subscription_create')
            billing_reason = invoice.get('billing_reason')
            amount = invoice.get('amount_paid', 0) / 100
            charge_id = invoice.get('charge')
            invoice_id = invoice.get('id')
            
            # Check if payment already exists for this invoice
            existing_payment = Payment.objects.filter(
                subscription=user_subscription,
                metadata__invoice_id=invoice_id
            ).first()
            
            if not existing_payment:
                # Check if this is initial payment and if payment was already created from checkout.session.completed
                if billing_reason == 'subscription_create':
                    # Check if payment exists from checkout session
                    checkout_payment = Payment.objects.filter(
                        subscription=user_subscription,
                        payment_type='subscription',
                        metadata__subscription_id=subscription_id
                    ).exclude(metadata__invoice_id=invoice_id).first()
                    
                    if not checkout_payment:
                        # Create payment record for initial subscription payment
                        Payment.objects.create(
                            user=user_subscription.user,
                            subscription=user_subscription,
                            payment_type='subscription',
                            amount=amount,
                            currency=invoice.get('currency', 'usd'),
                            status='succeeded',
                            stripe_charge_id=charge_id,
                            description=f'Subscription to {user_subscription.plan.display_name if user_subscription.plan else "Plan"}',
                            metadata={
                                'subscription_id': subscription_id,
                                'invoice_id': invoice_id,
                                'billing_reason': billing_reason,
                                'created_from': 'invoice.payment_succeeded'
                            }
                        )
                        logger.info(f"Initial subscription payment record created from invoice for subscription {subscription_id}, amount: ${amount}")
                else:
                    # This is a recurring payment, create a payment record
                    Payment.objects.create(
                        user=user_subscription.user,
                        subscription=user_subscription,
                        payment_type='subscription',
                        amount=amount,
                        currency=invoice.get('currency', 'usd'),
                        status='succeeded',
                        stripe_charge_id=charge_id,
                        description=f'Recurring payment for {user_subscription.plan.display_name if user_subscription.plan else "Subscription"}',
                        metadata={
                            'subscription_id': subscription_id,
                            'invoice_id': invoice_id,
                            'billing_reason': billing_reason
                        }
                    )
                    logger.info(f"Recurring payment record created for subscription {subscription_id}, amount: ${amount}")
            
            logger.info(f"Invoice payment succeeded for subscription {subscription_id}")
        except UserSubscription.DoesNotExist:
            logger.error(f"Subscription {subscription_id} not found")


def handle_invoice_payment_failed(invoice):
    """Handle failed invoice payment"""
    subscription_id = invoice.get('subscription')
    if subscription_id:
        try:
            user_subscription = UserSubscription.objects.get(stripe_subscription_id=subscription_id)
            user_subscription.status = 'past_due'
            user_subscription.save()
            logger.info(f"Invoice payment failed for subscription {subscription_id}")
        except UserSubscription.DoesNotExist:
            logger.error(f"Subscription {subscription_id} not found")

