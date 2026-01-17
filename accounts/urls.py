from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register('user-profiles', ProfileViewSet, basename='profiles')
router.register('contacts', ContactViewSet, basename='contact')

urlpatterns = [
    path('', include(router.urls)),
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('set-credentials/', SetCredentialsView.as_view(), name='set-credentials'),
    path('login/', LoginView.as_view(), name='login'),
    path('oauth/register/', OAuthRegisterView.as_view(), name='oauth-register'),
    path('oauth/login/', OAuthLoginView.as_view(), name='oauth-login'),
    # Password Reset Endpoints
    path('password-reset/send-otp/', SendPasswordResetOTPView.as_view(), name='send-password-reset-otp'),
    path('password-reset/verify-otp/', VerifyPasswordResetOTPView.as_view(), name='verify-password-reset-otp'),
    path('password-reset/reset/', ResetPasswordView.as_view(), name='reset-password'),
    # Admin endpoints
    path('admin/users/', AdminUsersListView.as_view(), name='admin-users'),
    path('admin/users/<int:user_id>/block/', AdminBlockUserView.as_view(), name='admin-block-user'),
    path('admin/users/<int:user_id>/unblock/', AdminBlockUserView.as_view(), name='admin-unblock-user'),
    path('admin/users/<int:user_id>/delete/', AdminDeleteUserView.as_view(), name='admin-delete-user'),
    path('admin/dashboard-analytics/', DashboardAnalyticsView.as_view(), name='dashboard-analytics'),
    path('admin/post-analytics/', PostAnalyticsView.as_view(), name='post-analytics'),
    path('admin/user-analytics/', UserAnalyticsView.as_view(), name='user-analytics'),
    path('admin/service-analytics/', ServiceAnalyticsView.as_view(), name='service-analytics'),
    path('admin/communities/', AdminCommunitiesListView.as_view(), name='admin-communities'),
    path('admin/communities/<int:community_id>/delete/', AdminDeleteCommunityView.as_view(), name='admin-delete-community'),
    # Public endpoints (for authenticated users)
    path('users/', PublicUsersListView.as_view(), name='public-users'),
    # Public stats endpoint (no authentication required)
    path('public/stats/', PublicStatsView.as_view(), name='public-stats'),
]