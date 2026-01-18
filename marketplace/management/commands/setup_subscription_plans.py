# setup_subscription_plans.py
import stripe
from django.core.management.base import BaseCommand
from django.conf import settings
from marketplace.models import SubscriptionPlan

stripe.api_key = settings.STRIPE_SECRET_KEY


class Command(BaseCommand):
    help = 'Setup default subscription plans in Stripe and database'

    def handle(self, *args, **options):
        self.stdout.write('Setting up subscription plans...')

        plans_data = [
            {
                'name': 'free',
                'display_name': 'Free',
                'price': 0.00,
                'posts_per_month': 1,
                'features': [
                    '1 post per month',
                    'Basic support',
                    'Standard visibility'
                ],
                'create_stripe': False  # Free plan doesn't need Stripe
            },
            {
                'name': 'basic',
                'display_name': 'Basic',
                'price': 9.99,
                'posts_per_month': 5,
                'features': [
                    '5 posts per month',
                    'Priority support',
                    'Enhanced visibility',
                    'Analytics dashboard'
                ],
                'create_stripe': True
            },
            {
                'name': 'pro',
                'display_name': 'Pro',
                'price': 19.99,
                'posts_per_month': 15,
                'features': [
                    '15 posts per month',
                    '24/7 priority support',
                    'Maximum visibility',
                    'Advanced analytics',
                    'Featured listings'
                ],
                'create_stripe': True
            },
            {
                'name': 'enterprise',
                'display_name': 'Enterprise',
                'price': 49.99,
                'posts_per_month': 0,  # 0 means unlimited
                'features': [
                    'Unlimited posts',
                    'Dedicated account manager',
                    'Custom branding',
                    'API access',
                    'White-label options'
                ],
                'create_stripe': True
            }
        ]

        for plan_data in plans_data:
            name = plan_data.pop('name')
            create_stripe = plan_data.pop('create_stripe')
            
            # Get or create plan in database
            plan, created = SubscriptionPlan.objects.get_or_create(
                name=name,
                defaults=plan_data
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created plan: {plan.display_name}')
                )
            else:
                # Update existing plan
                for key, value in plan_data.items():
                    setattr(plan, key, value)
                plan.save()
                self.stdout.write(
                    self.style.WARNING(f'Updated plan: {plan.display_name}')
                )

            # Create Stripe product and price if needed
            if create_stripe and not plan.stripe_price_id:
                try:
                    # Create Stripe product
                    product = stripe.Product.create(
                        name=plan.display_name,
                        description=f'{plan.display_name} subscription plan',
                        metadata={'plan_id': plan.id}
                    )
                    plan.stripe_product_id = product.id

                    # Create Stripe price
                    price = stripe.Price.create(
                        product=product.id,
                        unit_amount=int(plan.price * 100),  # Convert to cents
                        currency='usd',
                        recurring={'interval': 'month'},
                        metadata={'plan_id': plan.id}
                    )
                    plan.stripe_price_id = price.id
                    plan.save()

                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Created Stripe product and price for: {plan.display_name}'
                        )
                    )
                except stripe.error.StripeError as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'Failed to create Stripe product for {plan.display_name}: {str(e)}'
                        )
                    )
            elif create_stripe and plan.stripe_price_id:
                self.stdout.write(
                    self.style.WARNING(
                        f'Stripe product already exists for: {plan.display_name}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS('Subscription plans setup completed!')
        )

