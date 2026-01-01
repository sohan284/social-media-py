from rest_framework.routers import DefaultRouter
from django.urls import path, include
from interest.views import *
from post.views import *
from chats.views import *
from marketplace.views import *
from community.views import *

router = DefaultRouter()

""" User Interest Section """
router.register("categories", CategoryViewSet, basename="category")
router.register("subcategories", SubCategoryViewSet, basename="subcategory")

""" Post Section """
router.register(r'posts', PostViewSet, basename='post')
router.register(r'likes', LikeViewSet, basename='like')
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'shares', ShareViewSet, basename='share')
router.register(r'follows', FollowViewSet, basename='follow')
router.register(r'notifications', NotificationViewSet, basename='notification')

""" Marketplace Section """
router.register(r'marketplace/categories', MarketplaceCategoryViewSet, basename="marketplace-category")
router.register(r'marketplace/subcategories', MarketplaceSubCategoryViewSet, basename="marketplace-subcategory")
router.register(r'marketplace/items', MarketplaceProductViewSet, basename="marketplace-item")

""" Community Section """
router.register(r'communities', CommunityViewSet, basename='community')
router.register(r'join-requests', CommunityJoinRequestViewSet, basename='join-request')
router.register(r'invitations', CommunityInvitationViewSet, basename='invitation')

""" Chat Section """
router.register(r'chat/rooms', RoomViewSet, basename='chat-room')

urlpatterns = [
    # Community invitation endpoints (must be before router.urls to avoid conflicts)
    path('communities/invite/', InviteUserToCommunityView.as_view(), name='invite-user-to-community'),
    # Chat user endpoints
    path('chat/users/', ChatUserListView.as_view(), name='chat-users'),
    path('chat/users/search/', ChatUserSearchView.as_view(), name='chat-user-search'),
    # Direct messaging endpoints
    path('chat/messages/send/', SendDirectMessageView.as_view(), name='send-direct-message'),
    path('chat/messages/conversation/', GetConversationView.as_view(), name='get-conversation'),
    path('chat/messages/conversations/', GetConversationsListView.as_view(), name='get-conversations-list'),
    # Block and Report endpoints
    path('chat/block/', BlockUserView.as_view(), name='block-user'),
    path('chat/unblock/', UnblockUserView.as_view(), name='unblock-user'),
    path('chat/blocked-users/', BlockedUsersListView.as_view(), name='blocked-users-list'),
    path('chat/report/', ReportUserView.as_view(), name='report-user'),
    path('chat/reports/', UserReportsListView.as_view(), name='user-reports-list'),
    path('chat/reports/<int:report_id>/update/', UpdateReportStatusView.as_view(), name='update-report-status'),
    # Router URLs (must be last to avoid conflicts with specific paths)
    path("", include(router.urls)),
]
