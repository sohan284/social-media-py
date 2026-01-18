import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
import jwt
from django.conf import settings
from django.core.cache import cache
from .models import Room, Message

User = get_user_model()


class JWTAuthMiddleware(BaseMiddleware):
    """Custom middleware to authenticate WebSocket connections using JWT"""
    
    async def __call__(self, scope, receive, send):
        close_old_connections()
        
        # Get token from query string or headers
        query_string = scope.get('query_string', b'').decode()
        token = None
        
        # Try to get token from query string
        if query_string:
            params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            token = params.get('token')
        
        # Try to get token from headers
        if not token:
            headers = dict(scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        user = None
        if token:
            try:
                # Validate token
                UntypedToken(token)
                decoded_data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = decoded_data.get('user_id')
                if user_id:
                    user = await self.get_user(user_id)
            except (InvalidToken, TokenError, Exception):
                user = None
        
        scope['user'] = user
        return await super().__call__(scope, receive, send)
    
    @database_sync_to_async
    def get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None


""" Direct Message Consumer """
class DirectMessageConsumer(AsyncWebsocketConsumer):
    """ Consumer for Direct Messages with JWT authentication """
    
    async def connect(self):
        self.user = self.scope.get('user')

        # Check authentication
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Mark user as online
        await self.mark_user_online()
        
        # Join online status channel to receive updates
        await self.channel_layer.group_add('online_status', self.channel_name)
        
        # Broadcast online status to all users
        await self.broadcast_online_status(True)

        # Join user's personal channel for direct messages
        self.user_group = f'user_{self.user.id}'
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()
    
    async def online_status_change(self, event):
        """Handle online status change broadcasts"""
        await self.send(text_data=json.dumps({
            'type': 'online_status',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_online': event['is_online'],
        }))

    async def disconnect(self, code):
        # Mark user as offline
        await self.mark_user_offline()
        
        # Broadcast offline status to all users
        await self.broadcast_online_status(False)
        
        # Leave online status channel
        await self.channel_layer.group_discard('online_status', self.channel_name)
        
        # Leave user's personal channel
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
    
    @database_sync_to_async
    def mark_user_online(self):
        """Mark user as online in cache"""
        cache.set(f'user_online_{self.user.id}', True, timeout=300)  # 5 minutes timeout
    
    @database_sync_to_async
    def mark_user_offline(self):
        """Mark user as offline in cache"""
        cache.delete(f'user_online_{self.user.id}')
    
    async def broadcast_online_status(self, is_online):
        """Broadcast online status change to all connected users"""
        # Get all connected users and notify them
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        
        if channel_layer:
            # Broadcast to a general online status channel
            await channel_layer.group_send(
                'online_status',
                {
                    'type': 'online_status_change',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'is_online': is_online,
                }
            )

    async def direct_message(self, event):
        """Send direct message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message']
        }))
    
    async def message_request(self, event):
        """Send message request notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'message_request',
            'request': event['request']
        }))
    
    async def message_request_accepted(self, event):
        """Notify sender that message request was accepted"""
        await self.send(text_data=json.dumps({
            'type': 'message_request_accepted',
            'request': event['request']
        }))
    
    async def message_request_rejected(self, event):
        """Notify sender that message request was rejected"""
        await self.send(text_data=json.dumps({
            'type': 'message_request_rejected',
            'request': event['request']
        }))
    
    async def message_request_cancelled(self, event):
        """Notify receiver that message request was cancelled"""
        await self.send(text_data=json.dumps({
            'type': 'message_request_cancelled',
            'request': event['request']
        }))


""" Room-based Chat Consumer (for group chats) """
class ChatConsumer(AsyncWebsocketConsumer):
    """ Consumer for Chat with JWT authentication """
    
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group = f'chat_{self.room_id}'
        self.user = self.scope.get('user')

        # Check authentication
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        # Mark user as online
        await self.mark_user_online()
        
        # Join online status channel to receive updates
        await self.channel_layer.group_add('online_status', self.channel_name)
        
        # Broadcast online status to all users
        await self.broadcast_online_status(True)

        # Check if user has access to this room
        has_access = await self.check_room_access()
        if not has_access:
            await self.close()
            return

        # Join room
        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()
    
    async def online_status_change(self, event):
        """Handle online status change broadcasts"""
        await self.send(text_data=json.dumps({
            'type': 'online_status',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_online': event['is_online'],
        }))

    async def disconnect(self, code):
        # Mark user as offline (only if no other connections)
        await self.mark_user_offline()
        
        # Broadcast offline status to all users
        await self.broadcast_online_status(False)
        
        # Leave online status channel
        await self.channel_layer.group_discard('online_status', self.channel_name)
        
        # Leave room
        if hasattr(self, 'room_group'):
            await self.channel_layer.group_discard(self.room_group, self.channel_name)
    
    @database_sync_to_async
    def mark_user_online(self):
        """Mark user as online in cache"""
        cache.set(f'user_online_{self.user.id}', True, timeout=300)  # 5 minutes timeout
    
    @database_sync_to_async
    def mark_user_offline(self):
        """Mark user as offline in cache"""
        cache.delete(f'user_online_{self.user.id}')
    
    async def broadcast_online_status(self, is_online):
        """Broadcast online status change to all connected users"""
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        
        if channel_layer:
            await channel_layer.group_send(
                'online_status',
                {
                    'type': 'online_status_change',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'is_online': is_online,
                }
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_content = data.get('message', '').strip()
            
            if not message_content:
                return
            
            if not self.user or not self.user.is_authenticated:
                await self.send(text_data=json.dumps({
                    'error': 'Authentication required'
                }))
                return

            # Save to database
            message = await self.save_message(self.user, message_content)
            
            if message:
                # Broadcast to everyone in room
                await self.channel_layer.group_send(
                    self.room_group,
                    {
                        'type': 'chat_message',
                        'message': {
                            'id': message.id,
                            'content': message.content,
                            'sender_id': self.user.id,
                            'sender_username': self.user.username,
                            'room_id': self.room_id,
                            'created_at': message.created_at.isoformat(),
                            'is_read': message.is_read,
                        },
                    }
                )
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON format'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'error': str(e)
            }))

    async def chat_message(self, event):
        """Send message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message']  # Changed from 'data' to 'message' for consistency
        }))

    @database_sync_to_async
    def check_room_access(self):
        """Check if user has access to this room"""
        try:
            room = Room.objects.get(id=self.room_id)
            return self.user in room.participants.all()
        except Room.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, user, content):
        """Save message to database"""
        try:
            room = Room.objects.get(id=self.room_id)
            message = Message.objects.create(
                room=room,
                sender=user,
                content=content
            )
            # Update room's updated_at
            room.save()
            return message
        except Room.DoesNotExist:
            return None
    
""" End of Chat Consumer """