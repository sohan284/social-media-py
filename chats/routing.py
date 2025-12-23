from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/chat/<int:room_id>/', consumers.ChatConsumer.as_asgi()),  # For room-based chats (groups)
    path('ws/chat/direct/', consumers.DirectMessageConsumer.as_asgi()),  # For direct messaging
]