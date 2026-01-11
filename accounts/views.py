from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, permissions, status
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
import random
from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from .permissions import IsOwnerOrReadOnly, IsAdmin
from .email_templates import get_otp_verification_email_template, get_password_reset_email_template
from post.models import Post
from post.serializers import PostSerializer
from community.models import Community
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from post.models import Post
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.decorators import action
from .models import *
from .serializers import (
    SendOTPSerializer, VerifyOTPSerializer, SetCredentialsSerializer,
    LoginSerializer, OAuthRegisterSerializer, OAuthLoginSerializer,
    SendPasswordResetOTPSerializer, VerifyPasswordResetOTPSerializer, ResetPasswordSerializer,
    ProfileSerializer, ProfileUpdateSerializer, AdminUserSerializer, ContactSerializer
)
from post.models import *
from post.serializers import *
from .utils import *
import logging
from interest.models import *
from django.db import transaction
from marketplace.models import Product
from django.db.models import Sum, Avg, Max, Min

User = get_user_model()

logger = logging.getLogger(__name__)

from .utils import (
    verify_google_access_token, 
    verify_apple_access_token,
    get_google_user_info,
    get_apple_user_info
)


"""Generate JWT tokens"""
def tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    refresh['username'] = user.username
    refresh['email'] = user.email
    refresh['role'] = user.role if hasattr(user, 'role') else None
    refresh['username_set'] = user.username_set if hasattr(user, 'username_set') else None

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token)
    }


"""Email OTP Registration Flow"""
class SendOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = SendOTPSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        email = ser.validated_data['email'].lower()
        code = f"{random.randint(0, 999999):06d}"

        user, created = User.objects.get_or_create(
            email=email,
            defaults={'username': email.split('@')[0]}
        )
        user.verification_code = code
        user.email_verified = False
        user.is_oauth_user = False
        user.username_set = False
        user.save()

        # Send beautiful HTML email
        html_content = get_otp_verification_email_template(code)
        text_content = f'Your verification code is {code}. This code will expire in 10 minutes.'
        
        email = EmailMultiAlternatives(
            subject='Verify Your Email - Social Media Platform',
            body=text_content,
            from_email=settings.EMAIL_HOST_USER,
            to=[email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        return Response({
            "success": True,
            "message": "OTP sent to your email."
            }, status=201)


"""Verify Token"""
class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = VerifyOTPSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        email = ser.validated_data['email'].lower()
        code = ser.validated_data['code']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        if user.verification_code == code:
            user.email_verified = True
            user.verification_code = ''
            user.save()
            return Response({
                "success": True,
                "message": "Email verified successfully. Now set username and password."
                })

        return Response({
            "success": False,
            "error": "Invalid code"
            }, status=400)


# views.py - Updated SetCredentialsView
class SetCredentialsView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user = request.user if request.user and request.user.is_authenticated else None
        ser = SetCredentialsSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        if user is None:
            email = request.data.get('email')
            if not email:
                return Response({
                    "success": False,
                    "error": "If not authenticated, include 'email' field."
                }, status=400)
            try:
                user = User.objects.get(email=email.lower())
            except User.DoesNotExist:
                return Response({
                    "success": False,
                    "error": "User not found"
                }, status=404)
            if not user.email_verified:
                return Response({
                    "success": False,
                    "error": "Email not verified"
                }, status=400)

        if user.username_set:
            return Response({
                "success": False,
                "error": "Credentials already set."
            }, status=403)

        username = ser.validated_data['username']
        password = ser.validated_data['password']

        if User.objects.filter(username=username).exclude(pk=user.pk).exists():
            return Response({
                "success": False,
                "username": "Already taken."
            }, status=400)

        user.username = username
        user.set_password(password)
        user.username_set = True
        user.save()

        return Response({
            "success": True,
            "message": "Credentials set successfully. You are now logged in.",
            "tokens": tokens_for_user(user),
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role if hasattr(user, 'role') else 'user'
            }
        }, status=201)
        
"""Login View"""
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        if not ser.is_valid():
            return Response({
                "success": False,
                "message": "Invalid data",
                "details": ser.errors
                }, status=400)

        key = ser.validated_data['email_or_username']
        password = ser.validated_data['password']

        user = authenticate(username=key, password=password)
        if user is None:
            try:
                u = User.objects.get(email=key.lower())
                user = authenticate(username=u.username, password=password)
            except User.DoesNotExist:
                user = None

        if user is None:
            return Response({
                "success": False,
                "error": "Invalid credentials"
                }, status=401)

        # Allow admin users to login without email verification
        if not user.email_verified and user.role != 'admin':
            return Response({
                "success": False,
                "error": "Email not verified"
                }, status=403)
        
        return Response({
            "success": True,
            "message": "Login successful",
            "tokens": tokens_for_user(user),
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role
            }
            }, status=200)


""" Admin Users List View """
class AdminUsersListView(APIView):
    """Get all users for admin panel"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    
    def get(self, request):
        """Get all users with additional information"""
        from datetime import datetime
        from django.db.models import Q
        
        users = User.objects.select_related('profile').prefetch_related('profile__subcategories').all()
        
        # Filter by status (is_active)
        status_filter = request.query_params.get('status', None)
        if status_filter:
            if status_filter == 'active':
                users = users.filter(is_active=True)
            elif status_filter == 'inactive':
                users = users.filter(is_active=False)
        
        # Filter by date range
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        if start_date:
            try:
                date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                users = users.filter(date_joined__date__gte=date_obj)
            except (ValueError, TypeError):
                pass  # Invalid date format, ignore
        
        if end_date:
            try:
                date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                users = users.filter(date_joined__date__lte=date_obj)
            except (ValueError, TypeError):
                pass  # Invalid date format, ignore
        
        # Filter by search keyword (display_name or email)
        search_query = request.query_params.get('search', None)
        if search_query:
            search_query = search_query.strip()
            if search_query:
                users = users.filter(
                    Q(email__icontains=search_query) |
                    Q(profile__display_name__icontains=search_query) |
                    Q(username__icontains=search_query)
                )
        
        users = users.order_by('-date_joined')
        
        serializer = AdminUserSerializer(users, many=True, context={'request': request})
        
        return Response({
            "success": True,
            "data": serializer.data
        }, status=200)


""" Admin User Block/Unblock View """
class AdminBlockUserView(APIView):
    """Block or unblock a user (admin only)"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    
    def post(self, request, user_id):
        """Block a user"""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "User not found"
            }, status=404)
        
        # Prevent blocking yourself
        if user.id == request.user.id:
            return Response({
                "success": False,
                "error": "You cannot block yourself"
            }, status=400)
        
        # Prevent blocking other admins
        if user.role == 'admin' and user.id != request.user.id:
            return Response({
                "success": False,
                "error": "You cannot block other admin users"
            }, status=400)
        
        # Block user by setting is_active to False
        user.is_active = False
        user.save()
        
        return Response({
            "success": True,
            "message": f"User {user.username} has been blocked successfully"
        }, status=200)
    
    def delete(self, request, user_id):
        """Unblock a user"""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "User not found"
            }, status=404)
        
        # Unblock user by setting is_active to True
        user.is_active = True
        user.save()
        
        return Response({
            "success": True,
            "message": f"User {user.username} has been unblocked successfully"
        }, status=200)


""" Admin User Delete View """
class AdminDeleteUserView(APIView):
    """Delete a user (admin only)"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    
    def delete(self, request, user_id):
        """Delete a user"""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "User not found"
            }, status=404)
        
        # Prevent deleting yourself
        if user.id == request.user.id:
            return Response({
                "success": False,
                "error": "You cannot delete your own account"
            }, status=400)
        
        # Prevent deleting other admins
        if user.role == 'admin' and user.id != request.user.id:
            return Response({
                "success": False,
                "error": "You cannot delete other admin users"
            }, status=400)
        
        username = user.username
        # Delete the user (this will cascade delete the profile due to CASCADE relationship)
        user.delete()
        
        return Response({
            "success": True,
            "message": f"User {username} has been deleted successfully"
        }, status=200)


""" Admin Communities List View """
class AdminCommunitiesListView(APIView):
    """Get all communities (admin only)"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        try:
            from community.models import Community
            from community.serializers import CommunitySerializer
            from datetime import datetime
            
            from django.db.models import Q
            
            communities = Community.objects.all().select_related('created_by')
            
            # Filter by visibility
            visibility_filter = request.query_params.get('visibility', None)
            if visibility_filter and visibility_filter != 'all':
                communities = communities.filter(visibility=visibility_filter)
            
            # Filter by date range
            start_date = request.query_params.get('start_date', None)
            end_date = request.query_params.get('end_date', None)
            
            if start_date:
                try:
                    date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                    communities = communities.filter(created_at__date__gte=date_obj)
                except (ValueError, TypeError):
                    pass  # Invalid date format, ignore
            
            if end_date:
                try:
                    date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                    communities = communities.filter(created_at__date__lte=date_obj)
                except (ValueError, TypeError):
                    pass  # Invalid date format, ignore
            
            # Filter by search query
            search_query = request.query_params.get('search', None)
            if search_query:
                search_query = search_query.strip()
                if search_query:
                    communities = communities.filter(
                        Q(name__icontains=search_query) |
                        Q(title__icontains=search_query) |
                        Q(description__icontains=search_query) |
                        Q(created_by__username__icontains=search_query) |
                        Q(created_by__email__icontains=search_query)
                    )
            
            communities = communities.order_by('-created_at')
            
            serializer = CommunitySerializer(communities, many=True, context={'request': request})
            
            return Response({
                "success": True,
                "message": "Communities retrieved successfully",
                "data": serializer.data
            }, status=200)
        except Exception as e:
            logger.error(f"Error in AdminCommunitiesListView: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Error retrieving communities",
                "error": str(e)
            }, status=500)


""" Admin Community Delete View """
class AdminDeleteCommunityView(APIView):
    """Delete a community (admin only)"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def delete(self, request, community_id):
        """Delete a community"""
        try:
            from community.models import Community
            
            try:
                community = Community.objects.get(id=community_id)
            except Community.DoesNotExist:
                return Response({
                    "success": False,
                    "error": "Community not found"
                }, status=404)
            
            community_name = community.name
            # Delete the community (this will cascade delete related data)
            community.delete()
            
            return Response({
                "success": True,
                "message": f"Community {community_name} has been deleted successfully"
            }, status=200)
        except Exception as e:
            logger.error(f"Error in AdminDeleteCommunityView: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Error deleting community",
                "error": str(e)
            }, status=500)


""" Public Users List View """
class PublicUsersListView(APIView):
    """Get all users for authenticated users (not just admins)"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get all users with basic information"""
        users = User.objects.select_related('profile').all().order_by('-date_joined')
        
        # Use UserSerializer which is simpler and doesn't require admin
        from .serializers import UserSerializer
        serializer = UserSerializer(users, many=True, context={'request': request})
        
        return Response({
            "success": True,
            "data": serializer.data
        }, status=200)


""" Public Stats View """
class PublicStatsView(APIView):
    """Get public statistics for About Us page - no authentication required"""
    permission_classes = []  # Public endpoint
    
    def get(self, request):
        """Get basic platform statistics"""
        try:
            # Count active users (users who have verified email)
            total_users = User.objects.filter(email_verified=True).count()
            
            # Count approved posts (excluding shared posts)
            total_posts = Post.objects.filter(
                status='approved',
                shared_from__isnull=True
            ).count()
            
            # Count all communities
            total_communities = Community.objects.count()
            
            return Response({
                "success": True,
                "message": "Public statistics retrieved successfully",
                "data": {
                    "total_users": total_users,
                    "total_posts": total_posts,
                    "total_communities": total_communities,
                }
            }, status=200)
        except Exception as e:
            logger.error(f"Error in PublicStatsView: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Error retrieving public statistics",
                "error": str(e)
            }, status=500)


class DashboardAnalyticsView(APIView):
    """Get comprehensive dashboard analytics for admin panel"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        try:
            now = timezone.now()
            seven_days_ago = now - timedelta(days=7)
            thirty_days_ago = now - timedelta(days=30)
            ninety_days_ago = now - timedelta(days=90)
        
            # ========== BASIC COUNTS ==========
            total_users = User.objects.count()
            # Exclude shared posts from main count (shared posts are duplicates)
            total_posts = Post.objects.filter(shared_from__isnull=True).count()
            total_shared_posts = Post.objects.filter(shared_from__isnull=False).count()
            total_communities = Community.objects.count()
            total_products = Product.objects.count()
            total_comments = Comment.objects.count()
            total_likes = Like.objects.count()
            total_shares = Share.objects.count()
        
            # ========== POST STATUS BREAKDOWN ==========
            # Exclude shared posts from status breakdown
            approved_posts = Post.objects.filter(status='approved', shared_from__isnull=True).count()
            rejected_posts = Post.objects.filter(status='rejected', shared_from__isnull=True).count()
            pending_posts = Post.objects.filter(status='pending', shared_from__isnull=True).count()
            draft_posts = Post.objects.filter(status='draft', shared_from__isnull=True).count()
            approved_shared_posts = Post.objects.filter(status='approved', shared_from__isnull=False).count()
        
            # ========== POST TYPE BREAKDOWN ==========
            # Exclude shared posts from type breakdown
            text_posts = Post.objects.filter(post_type='text', shared_from__isnull=True).count()
            media_posts = Post.objects.filter(post_type='media', shared_from__isnull=True).count()
            link_posts = Post.objects.filter(post_type='link', shared_from__isnull=True).count()
        
            # ========== ENGAGEMENT METRICS ==========
            total_engagement = total_likes + (total_comments * 2) + (total_shares * 3)
            # Calculate averages excluding shared posts
            avg_likes_per_post = Post.objects.filter(shared_from__isnull=True).annotate(likes_count=Count('likes')).aggregate(
            avg=Avg('likes_count')
            )['avg'] or 0
            avg_comments_per_post = Post.objects.filter(shared_from__isnull=True).annotate(comments_count=Count('comments')).aggregate(
            avg=Avg('comments_count')
            )['avg'] or 0
            avg_shares_per_post = Post.objects.filter(shared_from__isnull=True).annotate(shares_count=Count('shares')).aggregate(
            avg=Avg('shares_count')
            )['avg'] or 0
        
            # ========== RECENT ACTIVITY (7 DAYS) ==========
            recent_users_7d = User.objects.filter(date_joined__gte=seven_days_ago).count()
            recent_posts_7d = Post.objects.filter(created_at__gte=seven_days_ago, shared_from__isnull=True).count()
            recent_shared_posts_7d = Post.objects.filter(created_at__gte=seven_days_ago, shared_from__isnull=False).count()
            recent_comments_7d = Comment.objects.filter(created_at__gte=seven_days_ago).count()
            recent_likes_7d = Like.objects.filter(created_at__gte=seven_days_ago).count()
            recent_shares_7d = Share.objects.filter(created_at__gte=seven_days_ago).count()
            recent_communities_7d = Community.objects.filter(created_at__gte=seven_days_ago).count()
            recent_products_7d = Product.objects.filter(created_at__gte=seven_days_ago).count()
        
            # ========== RECENT ACTIVITY (30 DAYS) ==========
            recent_users_30d = User.objects.filter(date_joined__gte=thirty_days_ago).count()
            recent_posts_30d = Post.objects.filter(created_at__gte=thirty_days_ago, shared_from__isnull=True).count()
            recent_shared_posts_30d = Post.objects.filter(created_at__gte=thirty_days_ago, shared_from__isnull=False).count()
            recent_comments_30d = Comment.objects.filter(created_at__gte=thirty_days_ago).count()
            recent_likes_30d = Like.objects.filter(created_at__gte=thirty_days_ago).count()
            recent_shares_30d = Share.objects.filter(created_at__gte=thirty_days_ago).count()
        
            # ========== USER ACTIVITY METRICS ==========
            # Get users who have been active (created posts, likes, or comments)
            # Simplified approach: count users who created posts (most reliable metric)
            try:
                # Count users who created posts in the last 7 days
                active_users_7d = User.objects.filter(posts__created_at__gte=seven_days_ago).distinct().count()
            except Exception as e:
                logger.error(f"Error calculating active_users_7d: {e}")
                active_users_7d = 0
            
            try:
                # Count users who created posts in the last 30 days
                active_users_30d = User.objects.filter(posts__created_at__gte=thirty_days_ago).distinct().count()
            except Exception as e:
                logger.error(f"Error calculating active_users_30d: {e}")
                active_users_30d = 0
            
            verified_users = User.objects.filter(email_verified=True).count()
            unverified_users = User.objects.filter(email_verified=False).count()
        
            # ========== COMMUNITY ANALYTICS ==========
            public_communities = Community.objects.filter(visibility='public').count()
            restricted_communities = Community.objects.filter(visibility='restricted').count()
            private_communities = Community.objects.filter(visibility='private').count()
        
            # Top 10 communities by members
            try:
                top_communities = Community.objects.annotate(
                    members_count_annotated=Count('members', distinct=True)
                ).order_by('-members_count_annotated')[:10]
            except:
                # Fallback to using cached members_count
                top_communities = Community.objects.order_by('-members_count')[:10]
            
            top_communities_data = [{
                'id': comm.id,
                'name': comm.name,
                'title': comm.title,
                'members_count': comm.members_count if hasattr(comm, 'members_count') else 0,
                'posts_count': comm.posts_count if hasattr(comm, 'posts_count') else 0,
                'visibility': comm.visibility,
            } for comm in top_communities]
        
            # ========== MARKETPLACE ANALYTICS ==========
            published_products = Product.objects.filter(status='published').count()
            draft_products = Product.objects.filter(status='draft').count()
            sold_products = Product.objects.filter(status='sold').count()
            unpublished_products = Product.objects.filter(status='unpublished').count()
        
            # Product price analytics
            price_stats = Product.objects.filter(status='published').aggregate(
                avg_price=Avg('price'),
                max_price=Max('price'),
                min_price=Min('price'),
                total_value=Sum('price')
            )
        
            # ========== ACTIVITY TIMELINE (30 DAYS) ==========
            activity_data = []
            for i in range(30):
                day_start = thirty_days_ago + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                # Exclude shared posts from activity timeline
                day_posts = Post.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end,
                    shared_from__isnull=True
                ).count()
                
                day_users = User.objects.filter(
                    date_joined__gte=day_start,
                    date_joined__lt=day_end
                ).count()
                
                day_likes = Like.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end
                ).count()
                
                day_comments = Comment.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end
                ).count()
                
                day_shares = Share.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end
                ).count()
                
                activity_data.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'posts': day_posts,
                    'users': day_users,
                    'likes': day_likes,
                    'comments': day_comments,
                    'shares': day_shares,
                })
        
            # ========== ENGAGEMENT TIMELINE (30 DAYS) ==========
            engagement_timeline = []
            for i in range(30):
                day_start = thirty_days_ago + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                day_likes = Like.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end
                ).count()
                
                day_comments = Comment.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end
                ).count()
                
                day_shares = Share.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end
                ).count()
                
                engagement_timeline.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'likes': day_likes,
                    'comments': day_comments,
                    'shares': day_shares,
                    'total': day_likes + (day_comments * 2) + (day_shares * 3),
                })
        
            # ========== TOP POSTS ==========
            # Top 10 most liked posts (exclude shared posts)
            top_liked_posts = Post.objects.filter(shared_from__isnull=True).annotate(
                likes_count_annotated=Count('likes')
            ).select_related('user', 'user__profile').prefetch_related('likes', 'comments', 'shares').order_by('-likes_count_annotated')[:10]
        
            # Top 10 most commented posts (exclude shared posts)
            top_commented_posts = Post.objects.filter(shared_from__isnull=True).annotate(
                comments_count_annotated=Count('comments')
            ).select_related('user', 'user__profile').prefetch_related('likes', 'comments', 'shares').order_by('-comments_count_annotated')[:10]
            
            # Top 10 most shared posts (exclude shared posts from this list)
            top_shared_posts = Post.objects.filter(shared_from__isnull=True).annotate(
                shares_count_annotated=Count('shares')
            ).select_related('user', 'user__profile').prefetch_related('likes', 'comments', 'shares').order_by('-shares_count_annotated')[:10]
            
            # Top 10 by engagement score (exclude shared posts)
            top_engagement_posts = Post.objects.filter(shared_from__isnull=True).annotate(
                likes_count=Count('likes'),
                comments_count=Count('comments'),
                shares_count=Count('shares'),
                engagement_score=Count('likes') + (Count('comments') * 2) + (Count('shares') * 3)
            ).select_related('user', 'user__profile').order_by('-engagement_score')[:10]
        
            top_liked_serializer = PostSerializer(top_liked_posts, many=True, context={'request': request})
            top_commented_serializer = PostSerializer(top_commented_posts, many=True, context={'request': request})
            top_shared_serializer = PostSerializer(top_shared_posts, many=True, context={'request': request})
            top_engagement_serializer = PostSerializer(top_engagement_posts, many=True, context={'request': request})
        
            # ========== USER GROWTH TREND (90 DAYS) ==========
            user_growth = []
            for i in range(90):
                day_start = ninety_days_ago + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                cumulative_users = User.objects.filter(date_joined__lt=day_end).count()
                new_users_today = User.objects.filter(
                    date_joined__gte=day_start,
                    date_joined__lt=day_end
                ).count()
                
                user_growth.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'cumulative': cumulative_users,
                    'new': new_users_today,
                })
            
            # ========== POST GROWTH TREND (90 DAYS) ==========
            post_growth = []
            for i in range(90):
                day_start = ninety_days_ago + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                # Exclude shared posts from growth trend
                cumulative_posts = Post.objects.filter(created_at__lt=day_end, shared_from__isnull=True).count()
                new_posts_today = Post.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end,
                    shared_from__isnull=True
                ).count()
                
                post_growth.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'cumulative': cumulative_posts,
                    'new': new_posts_today,
                })
            
            return Response({
            "success": True,
            "message": "Dashboard analytics retrieved successfully",
            "data": {
                # Basic counts
                "total_users": total_users,
                "total_posts": total_posts,
                "total_shared_posts": total_shared_posts,
                "total_communities": total_communities,
                "total_products": total_products,
                "total_comments": total_comments,
                "total_likes": total_likes,
                "total_shares": total_shares,
                "total_engagement": total_engagement,
                
                # Post status breakdown
                "post_status": {
                    "approved": approved_posts,
                    "rejected": rejected_posts,
                    "pending": pending_posts,
                    "draft": draft_posts,
                    "approved_shared": approved_shared_posts,
                },
                
                # Post type breakdown
                "post_types": {
                    "text": text_posts,
                    "media": media_posts,
                    "link": link_posts,
                },
                
                # Engagement averages
                "engagement_averages": {
                    "avg_likes_per_post": round(avg_likes_per_post, 2),
                    "avg_comments_per_post": round(avg_comments_per_post, 2),
                    "avg_shares_per_post": round(avg_shares_per_post, 2),
                },
                
                # Recent activity (7 days)
                "recent_activity_7d": {
                    "new_users": recent_users_7d,
                    "new_posts": recent_posts_7d,
                    "new_shared_posts": recent_shared_posts_7d,
                    "new_comments": recent_comments_7d,
                    "new_likes": recent_likes_7d,
                    "new_shares": recent_shares_7d,
                    "new_communities": recent_communities_7d,
                    "new_products": recent_products_7d,
                },
                
                # Recent activity (30 days)
                "recent_activity_30d": {
                    "new_users": recent_users_30d,
                    "new_posts": recent_posts_30d,
                    "new_shared_posts": recent_shared_posts_30d,
                    "new_comments": recent_comments_30d,
                    "new_likes": recent_likes_30d,
                    "new_shares": recent_shares_30d,
                },
                
                # User activity
                "user_activity": {
                    "active_users_7d": active_users_7d,
                    "active_users_30d": active_users_30d,
                    "verified_users": verified_users,
                    "unverified_users": unverified_users,
                },
                
                # Community analytics
                "community_analytics": {
                    "public": public_communities,
                    "restricted": restricted_communities,
                    "private": private_communities,
                    "top_communities": top_communities_data,
                },
                
                # Marketplace analytics
                "marketplace_analytics": {
                    "published": published_products,
                    "draft": draft_products,
                    "sold": sold_products,
                    "unpublished": unpublished_products,
                    "price_stats": {
                        "avg_price": float(price_stats['avg_price'] or 0),
                        "max_price": float(price_stats['max_price'] or 0),
                        "min_price": float(price_stats['min_price'] or 0),
                        "total_value": float(price_stats['total_value'] or 0),
                    },
                },
                
                # Activity timeline (30 days)
                "activity_timeline": activity_data,
                
                # Engagement timeline (30 days)
                "engagement_timeline": engagement_timeline,
                
                # User growth (90 days)
                "user_growth": user_growth,
                
                # Post growth (90 days)
                "post_growth": post_growth,
                
                # Top posts
                "top_posts": {
                    "most_liked": top_liked_serializer.data,
                    "most_commented": top_commented_serializer.data,
                    "most_shared": top_shared_serializer.data,
                    "most_engagement": top_engagement_serializer.data,
                },
            }
        }, status=200)
        except Exception as e:
            logger.error(f"Error in DashboardAnalyticsView: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Error retrieving dashboard analytics",
                "error": str(e)
            }, status=500)


class PostAnalyticsView(APIView):
    """Get filtered post analytics based on date range"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        try:
            from datetime import datetime
            
            # Get date range parameters
            start_date_str = request.query_params.get('start_date')
            end_date_str = request.query_params.get('end_date')
            
            now = timezone.now()
            
            # Parse dates or use defaults
            if start_date_str:
                try:
                    start_date = timezone.make_aware(datetime.strptime(start_date_str, '%Y-%m-%d'))
                except ValueError:
                    start_date = now - timedelta(days=30)
            else:
                start_date = now - timedelta(days=30)
            
            if end_date_str:
                try:
                    end_date = timezone.make_aware(datetime.strptime(end_date_str, '%Y-%m-%d'))
                    # Include the full end date
                    end_date = end_date.replace(hour=23, minute=59, second=59)
                except ValueError:
                    end_date = now
            else:
                end_date = now
            
            # Ensure start_date is before end_date
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            
            # Calculate number of days
            days_diff = (end_date - start_date).days + 1
            
            # Limit to reasonable range (max 2 years)
            if days_diff > 730:
                days_diff = 730
                start_date = end_date - timedelta(days=729)
            
            # Generate daily post analytics data
            post_analytics = []
            
            for i in range(days_diff):
                day_start = start_date + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                # Post analytics (exclude shared posts) - only new posts per day
                new_posts = Post.objects.filter(
                    created_at__gte=day_start,
                    created_at__lt=day_end,
                    shared_from__isnull=True
                ).count()
                
                post_analytics.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'new': new_posts,
                })
            
            return Response({
                "success": True,
                "message": "Post analytics retrieved successfully",
                "data": {
                    "post_analytics": post_analytics,
                    "date_range": {
                        "start_date": start_date.strftime('%Y-%m-%d'),
                        "end_date": end_date.strftime('%Y-%m-%d'),
                        "days": days_diff,
                    }
                }
            }, status=200)
        except Exception as e:
            logger.error(f"Error in PostAnalyticsView: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Error retrieving post analytics",
                "error": str(e)
            }, status=500)


class UserAnalyticsView(APIView):
    """Get filtered user analytics based on date range"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get(self, request):
        try:
            from datetime import datetime
            
            # Get date range parameters
            start_date_str = request.query_params.get('start_date')
            end_date_str = request.query_params.get('end_date')
            
            now = timezone.now()
            
            # Parse dates or use defaults
            if start_date_str:
                try:
                    start_date = timezone.make_aware(datetime.strptime(start_date_str, '%Y-%m-%d'))
                except ValueError:
                    start_date = now - timedelta(days=30)
            else:
                start_date = now - timedelta(days=30)
            
            if end_date_str:
                try:
                    end_date = timezone.make_aware(datetime.strptime(end_date_str, '%Y-%m-%d'))
                    # Include the full end date
                    end_date = end_date.replace(hour=23, minute=59, second=59)
                except ValueError:
                    end_date = now
            else:
                end_date = now
            
            # Ensure start_date is before end_date
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            
            # Calculate number of days
            days_diff = (end_date - start_date).days + 1
            
            # Limit to reasonable range (max 2 years)
            if days_diff > 730:
                days_diff = 730
                start_date = end_date - timedelta(days=729)
            
            # Generate daily user analytics data
            user_analytics = []
            
            for i in range(days_diff):
                day_start = start_date + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                # User analytics - only new users per day
                new_users = User.objects.filter(
                    date_joined__gte=day_start,
                    date_joined__lt=day_end
                ).count()
                
                user_analytics.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'new': new_users,
                })
            
            return Response({
                "success": True,
                "message": "User analytics retrieved successfully",
                "data": {
                    "user_analytics": user_analytics,
                    "date_range": {
                        "start_date": start_date.strftime('%Y-%m-%d'),
                        "end_date": end_date.strftime('%Y-%m-%d'),
                        "days": days_diff,
                    }
                }
            }, status=200)
        except Exception as e:
            logger.error(f"Error in UserAnalyticsView: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": "Error retrieving user analytics",
                "error": str(e)
            }, status=500)

    
""" User Profile Section """
class ProfileViewSet(viewsets.ModelViewSet):
    queryset = Profile.objects.all()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def get_serializer_class(self):
        """Use different serializers for read and write operations"""
        if self.action in ['update', 'partial_update']:
            return ProfileUpdateSerializer
        return ProfileSerializer

    def get_queryset(self):
        """Return all profiles for list view"""
        return Profile.objects.select_related('user').all().order_by('-created_at')

    def create(self, request, *args, **kwargs):
        """
        Prevent manual profile creation - profiles are auto-created with user.
        """
        return Response({
            "success": False,
            "error": "Profiles are automatically created with user accounts. Use PUT/PATCH to update your profile."},
            status=status.HTTP_403_FORBIDDEN
        )

    def update(self, request, *args, **kwargs):
        """Only the profile owner can update their profile."""
        profile = self.get_object()
        
        if profile.user != request.user:
            return Response({
                "success": False,
                "error": "You do not have permission to edit this profile."
            })
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Only the profile owner can partially update their profile."""
        profile = self.get_object()
        
        if profile.user != request.user:
            return Response({
                "success": False,
                "error": "You do not have permission to edit this profile."
            })
        
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Prevent profile deletion - profiles should exist as long as user exists.
        If you want to delete profile, delete the user account instead.
        """
        return Response(
            {
                "success": False,
                "error": "Profiles cannot be deleted directly. Delete the user account to remove the profile."},
            status=status.HTTP_403_FORBIDDEN
        )

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get the current user's profile"""
        if not request.user.is_authenticated:
            return Response(
                {
                    "success": False,
                    "error": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        profile = get_object_or_404(Profile, user=request.user)
        serializer = self.get_serializer(profile)
        return Response({
            "success": True,
            "message": "Data retrieved successfully",
            "data": serializer.data
            })

    @action(detail=False, methods=['put', 'patch'])
    def update_me(self, request):
        """Update the current user's profile"""
        if not request.user.is_authenticated:
            return Response(
                {
                    "success": False,
                    "error": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        profile = get_object_or_404(Profile, user=request.user)
        serializer = ProfileUpdateSerializer(
            profile, 
            data=request.data, 
            partial=request.method == 'PATCH',
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            # Return full profile data
            response_serializer = ProfileSerializer(profile, context={'request': request})
            return Response({
                "success": True,
                "message": "Profile updated successfullty.",
                "data": response_serializer.data})
        
        return Response({
            "success": False,
            "error": "Invalid data.",
            "details": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search profiles by username or display name"""
        query = request.query_params.get('q', '')
        
        if not query:
            return Response({
                "success": False,
                "error": "Please provide a search query using ?q=searchterm"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        profiles = Profile.objects.filter(
            models.Q(user__username__icontains=query) |
            models.Q(display_name__icontains=query)
        ).select_related('user').order_by('-created_at')
        
        page = self.paginate_queryset(profiles)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(profiles, many=True)
        return Response({
            "success": True,
            "message": "Data retrieved successfully.",
            "data" : serializer.data})
    

"""OAuth Register View - Using Access Token"""
class OAuthRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Log incoming request data for debugging
        logger.info(f"OAuth Register Request Data: {request.data}")
        
        serializer = OAuthRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            logger.error(f"Serializer Validation Error: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        access_token = serializer.validated_data['access_token']
        provider = serializer.validated_data['provider'].lower()

        logger.info(f"Provider: {provider}")

        # Verify access token and get user email based on provider
        email = None
        user_info = None

        try:
            if provider == 'google':
                # For Google: Use userinfo endpoint (PRIMARY METHOD)
                user_info = get_google_user_info(access_token)
                if user_info:
                    email = user_info.get('email')
                    logger.info(f"Google user info retrieved: {user_info}")
                else:
                    # Fallback: Try tokeninfo endpoint
                    email = verify_google_access_token(access_token)
                    logger.info(f"Google tokeninfo result: {email}")

            elif provider == 'apple':
                # For Apple: Verify JWT token
                email = verify_apple_access_token(access_token)
                logger.info(f"Apple token verification result: {email}")
                
                # Fallback: Get user info without verification
                if not email:
                    user_info = get_apple_user_info(access_token)
                    if user_info:
                        email = user_info.get('email')
                        logger.info(f"Apple user info: {user_info}")
            else:
                return Response(
                    {"error": "Unsupported provider. Use 'google' or 'apple'."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not email:
                logger.error(f"Failed to get email from {provider} token")
                return Response(
                    {
                        "error": f"Invalid {provider} access token or unable to retrieve user information.",
                        "details": "Please ensure the token is valid and has not expired."
                    }, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Generate username from email (part before @)
            base_username = email.split('@')[0].lower()
            # Remove special characters from username
            base_username = ''.join(c if c.isalnum() or c in ['_', '.'] else '_' for c in base_username)
            username = base_username

            # Check if user already exists
            try:
                existing_user = User.objects.get(email=email)
                logger.info(f"User already exists: {email}")
                return Response(
                    {
                        "message": "User already registered with this email.",
                        "email": email,
                        "username": existing_user.username,
                        "provider": provider
                    }, 
                    status=status.HTTP_200_OK
                )
            except User.DoesNotExist:
                pass

            # Ensure username is unique
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            # Create new user
            user = User.objects.create(
                email=email,
                username=username,
                email_verified=True,
                is_oauth_user=True,
                username_set=True
            )

            # Set unusable password for OAuth users
            user.set_unusable_password()
            user.save()

            logger.info(f"User created successfully: {email}")

            return Response(
                {
                    "message": f"User registered successfully via {provider.title()}.",
                    "email": email,
                    "username": username,
                    "provider": provider
                }, 
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"OAuth Register Error: {str(e)}", exc_info=True)
            return Response(
                {"error": f"An error occurred during registration: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""OAuth Login View - Using Access Token"""
class OAuthLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Log incoming request data for debugging
        logger.info(f"OAuth Login Request Data: {request.data}")
        
        serializer = OAuthLoginSerializer(data=request.data)
        if not serializer.is_valid():
            logger.error(f"Serializer Validation Error: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        access_token = serializer.validated_data['access_token']
        provider = serializer.validated_data['provider'].lower()

        logger.info(f"Provider: {provider}")

        # Verify access token and get user email based on provider
        email = None
        user_info = None

        try:
            if provider == 'google':
                # For Google: Use userinfo endpoint (PRIMARY METHOD)
                user_info = get_google_user_info(access_token)
                if user_info:
                    email = user_info.get('email')
                    logger.info(f"Google user info retrieved: {user_info}")
                else:
                    # Fallback: Try tokeninfo endpoint
                    email = verify_google_access_token(access_token)
                    logger.info(f"Google tokeninfo result: {email}")

            elif provider == 'apple':
                # For Apple: Verify JWT token
                email = verify_apple_access_token(access_token)
                logger.info(f"Apple token verification result: {email}")
                
                # Fallback: Get user info without verification
                if not email:
                    user_info = get_apple_user_info(access_token)
                    if user_info:
                        email = user_info.get('email')
                        logger.info(f"Apple user info: {user_info}")
            else:
                return Response(
                    {"error": "Unsupported provider. Use 'google' or 'apple'."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not email:
                logger.error(f"Failed to get email from {provider} token")
                return Response(
                    {
                        "error": f"Invalid {provider} access token or unable to retrieve user information.",
                        "details": "Please ensure the token is valid and has not expired."
                    }, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if user exists
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                logger.error(f"User not found: {email}")
                return Response(
                    {
                        "error": "User not registered. Please register first.",
                        "email": email
                    }, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Verify user is an OAuth user
            if not user.is_oauth_user:
                logger.error(f"User is not OAuth user: {email}")
                return Response(
                    {"error": "This account was not registered via OAuth. Please use email/password login."}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            # Generate tokens
            tokens = tokens_for_user(user)

            logger.info(f"User logged in successfully: {email}")

            return Response(
                {
                    "message": f"Logged in successfully via {provider.title()}.",
                    "tokens": tokens,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "username": user.username,
                        "provider": provider
                    }
                }, 
                status=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"OAuth Login Error: {str(e)}", exc_info=True)
            return Response(
                {"error": f"An error occurred during login: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""Password Reset Flow"""
class SendPasswordResetOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = SendPasswordResetOTPSerializer(data=request.data)
        if not ser.is_valid():
            return Response({
                "success": False,
                "error": "Invalid data",
                "details": ser.errors
            }, status=400)

        email = ser.validated_data['email'].lower()
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal if user exists or not for security
            return Response({
                "success": True,
                "message": "If an account exists with this email, an OTP has been sent."
            }, status=200)

        # Generate OTP
        code = f"{random.randint(0, 999999):06d}"
        user.verification_code = code
        user.save()

        # Send beautiful HTML email
        html_content = get_password_reset_email_template(code)
        text_content = f'Your password reset verification code is {code}. This code will expire in 10 minutes.'
        
        email = EmailMultiAlternatives(
            subject='Reset Your Password - Social Media Platform',
            body=text_content,
            from_email=settings.EMAIL_HOST_USER,
            to=[email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        return Response({
            "success": True,
            "message": "If an account exists with this email, an OTP has been sent."
        }, status=200)


class VerifyPasswordResetOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = VerifyPasswordResetOTPSerializer(data=request.data)
        if not ser.is_valid():
            return Response({
                "success": False,
                "error": "Invalid data",
                "details": ser.errors
            }, status=400)

        email = ser.validated_data['email'].lower()
        code = ser.validated_data['code']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "User not found"
            }, status=404)

        if user.verification_code == code:
            return Response({
                "success": True,
                "message": "OTP verified successfully. You can now reset your password."
            }, status=200)

        return Response({
            "success": False,
            "error": "Invalid or expired OTP"
        }, status=400)


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = ResetPasswordSerializer(data=request.data)
        if not ser.is_valid():
            return Response({
                "success": False,
                "error": "Invalid data",
                "details": ser.errors
            }, status=400)

        email = ser.validated_data['email'].lower()
        code = ser.validated_data['code']
        new_password = ser.validated_data['new_password']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "User not found"
            }, status=404)

        # Verify OTP
        if user.verification_code != code:
            return Response({
                "success": False,
                "error": "Invalid or expired OTP"
            }, status=400)

        # Reset password
        user.set_password(new_password)
        user.verification_code = ''  # Clear OTP after use
        user.save()

        return Response({
            "success": True,
            "message": "Password reset successfully. You can now login with your new password."
        }, status=200)


""" Contact Section """
class ContactViewSet(viewsets.ModelViewSet):
    """ViewSet for Contact form submissions"""
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    
    def get_permissions(self):
        """Allow anyone to create contacts, but only admins can view/list/delete"""
        if self.action == 'create':
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAuthenticated, IsAdmin]
        return [permission() for permission in permission_classes]
    
    def create(self, request, *args, **kwargs):
        """Create a new contact submission"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response({
            "success": True,
            "message": "Thank you for contacting us! We'll get back to you soon.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)
    
    def list(self, request, *args, **kwargs):
        """List all contact submissions (admin only)"""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                "success": True,
                "message": "Contacts retrieved successfully",
                "data": serializer.data
            })
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "success": True,
            "message": "Contacts retrieved successfully",
            "data": serializer.data
        })
    
    def retrieve(self, request, *args, **kwargs):
        """Retrieve a specific contact submission"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            "success": True,
            "message": "Contact retrieved successfully",
            "data": serializer.data
        })
    
    def destroy(self, request, *args, **kwargs):
        """Delete a contact submission (admin only)"""
        try:
            instance = self.get_object()
            contact_name = f"{instance.first_name} {instance.last_name}"
            self.perform_destroy(instance)
            return Response({
                "success": True,
                "message": f"Contact from {contact_name} has been deleted successfully"
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['patch'])
    def mark_read(self, request, pk=None):
        """Mark a contact submission as read"""
        contact = self.get_object()
        contact.is_read = True
        contact.read_at = timezone.now()
        contact.read_by = request.user
        contact.save()
        
        serializer = self.get_serializer(contact)
        return Response({
            "success": True,
            "message": "Contact marked as read",
            "data": serializer.data
        })