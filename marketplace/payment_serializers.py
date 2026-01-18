# payment_serializers.py
from rest_framework import serializers
from .models import SubscriptionPlan, UserSubscription, Payment, PostCredit
from django.contrib.auth import get_user_model

User = get_user_model()


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'display_name', 'price', 'posts_per_month', 'features', 'is_active']
        read_only_fields = ['id']


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    plan_id = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.filter(is_active=True),
        source='plan',
        write_only=True,
        required=False
    )
    remaining_posts = serializers.SerializerMethodField()
    
    class Meta:
        model = UserSubscription
        fields = [
            'id', 'user', 'plan', 'plan_id', 'status', 'current_period_start',
            'current_period_end', 'posts_used_this_month', 'remaining_posts',
            'cancel_at_period_end', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
    
    def get_remaining_posts(self, obj):
        return obj.get_remaining_posts()


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'user', 'subscription', 'payment_type', 'amount', 'currency',
            'status', 'description', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class PostCreditSerializer(serializers.ModelSerializer):
    remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = PostCredit
        fields = ['id', 'user', 'amount', 'used', 'remaining', 'expires_at', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_remaining(self, obj):
        return obj.amount - obj.used


class SubscriptionUsageSerializer(serializers.Serializer):
    """Serializer for subscription usage information"""
    has_subscription = serializers.BooleanField()
    plan_name = serializers.CharField(allow_null=True)
    posts_used = serializers.IntegerField()
    posts_limit = serializers.IntegerField(allow_null=True)  # None means unlimited
    remaining_posts = serializers.IntegerField(allow_null=True)
    can_post = serializers.BooleanField()
    has_credits = serializers.BooleanField()
    credit_count = serializers.IntegerField()

