# models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils import timezone

User = get_user_model()

class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if self.slug is None:
            self.slug = slugify(self.name)
        return super(Category, self).save(*args, **kwargs)

    
class SubCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (self.category.name + ' - ' + self.name)
    class Meta:
        verbose_name_plural = 'Sub Categories'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if self.slug is None:
            self.slug = slugify(self.name)
        return super(SubCategory, self).save(*args, **kwargs)

class Product(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('sold', 'Sold'),
        ('unpublished', 'Unpublished'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='products')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    sub_category = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name='products')
    description = models.TextField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    link = models.URLField(max_length=500, help_text="Link to the service platform")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['-created_at']


# Payment Models
class SubscriptionPlan(models.Model):
    """Subscription plans for promotion posts"""
    PLAN_TIERS = (
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    )
    
    name = models.CharField(max_length=50, unique=True, help_text="Unique identifier for the plan (e.g., 'premium', 'starter')")
    display_name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    posts_per_month = models.IntegerField(default=0)  # 0 means unlimited
    stripe_price_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stripe Price ID for subscription")
    stripe_product_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stripe Product ID")
    is_active = models.BooleanField(default=True)
    is_recommended = models.BooleanField(default=False, help_text="Mark this plan as recommended")
    features = models.JSONField(default=list, help_text="List of features for this plan")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.display_name} - ${self.price}/month"
    
    class Meta:
        ordering = ['price']


class UserSubscription(models.Model):
    """User subscription tracking"""
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('canceled', 'Canceled'),
        ('past_due', 'Past Due'),
        ('trialing', 'Trialing'),
        ('incomplete', 'Incomplete'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    stripe_subscription_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    posts_used_this_month = models.IntegerField(default=0)
    last_reset_date = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.plan.display_name if self.plan else 'No Plan'}"
    
    def reset_monthly_usage(self):
        """Reset monthly post count"""
        from django.utils import timezone
        now = timezone.now()
        if self.last_reset_date.month != now.month or self.last_reset_date.year != now.year:
            self.posts_used_this_month = 0
            self.last_reset_date = now
            self.save()
    
    def can_post(self):
        """Check if user can post based on their subscription"""
        self.reset_monthly_usage()
        
        if not self.plan:
            # Free tier - 1 post per month
            return self.posts_used_this_month < 1
        
        if self.plan.posts_per_month == 0:
            # Unlimited plan
            return True
        
        return self.posts_used_this_month < self.plan.posts_per_month
    
    def get_remaining_posts(self):
        """Get remaining posts for current month"""
        self.reset_monthly_usage()
        
        if not self.plan:
            return max(0, 1 - self.posts_used_this_month)
        
        if self.plan.posts_per_month == 0:
            return -1  # Unlimited
        
        return max(0, self.plan.posts_per_month - self.posts_used_this_month)
    
    class Meta:
        ordering = ['-created_at']


class Payment(models.Model):
    """Payment history tracking"""
    PAYMENT_TYPES = (
        ('subscription', 'Subscription'),
        ('one_time', 'One Time Post'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    subscription = models.ForeignKey(UserSubscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='usd')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - ${self.amount} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']


class PostCredit(models.Model):
    """One-time post purchase credits"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_credits')
    amount = models.IntegerField(default=1, help_text="Number of posts purchased")
    used = models.IntegerField(default=0)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='credits')
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.amount - self.used} credits remaining"
    
    def has_credits(self):
        """Check if user has available credits"""
        from django.utils import timezone
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return (self.amount - self.used) > 0
    
    def use_credit(self):
        """Use one credit"""
        if self.has_credits():
            self.used += 1
            self.save()
            return True
        return False
    
    class Meta:
        ordering = ['-created_at']
