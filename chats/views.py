from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, Max
from django.contrib.auth import get_user_model
from .models import Room, Message
from .serializers import RoomSerializer, MessageSerializer
from accounts.serializers import UserSerializer
from post.models import Follow

User = get_user_model()

""" Viewset for Chat """
class RoomViewSet(viewsets.ModelViewSet):
    """ Viewset for Room """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RoomSerializer

    def get_queryset(self):
        """Get rooms where current user is a participant"""
        return Room.objects.filter(participants=self.request.user).annotate(
            last_message_time=Max('messages__created_at')
        ).order_by('-last_message_time', '-updated_at').distinct()

    def create(self, request, *args, **kwargs):
        """Create a chat room (one-on-one or group)"""
        participant_id = request.data.get('participant_id')
        name = request.data.get('name')
        member_ids = request.data.get('member_ids', [])  # List of user IDs to add to group
        
        # If participant_id is provided, create/find one-on-one chat
        if participant_id:
            try:
                other_user = User.objects.get(id=participant_id)
            except User.DoesNotExist:
                return Response({
                    "success": False,
                    "error": "User not found"
                }, status=status.HTTP_404_NOT_FOUND)
            
            if other_user == request.user:
                return Response({
                    "success": False,
                    "error": "Cannot create chat with yourself"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if room already exists
            existing_room = Room.objects.filter(
                is_group=False,
                participants=request.user
            ).filter(participants=other_user).distinct().first()
            
            if existing_room:
                serializer = self.get_serializer(existing_room, context={'request': request})
                return Response({
                    "success": True,
                    "message": "Room already exists",
                    "data": serializer.data
                }, status=status.HTTP_200_OK)
            
            # Create new one-on-one room
            room = Room.objects.create(is_group=False)
            room.participants.add(request.user, other_user)
            serializer = self.get_serializer(room, context={'request': request})
            return Response({
                "success": True,
                "message": "Room created successfully",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
        
        # Create group room
        if not name or not name.strip():
            return Response({
                "success": False,
                "error": "Room name is required for group chats"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        room = Room.objects.create(is_group=True, name=name.strip())
        room.participants.add(request.user)  # Creator is automatically added
        room.admins.add(request.user)  # Creator is automatically an admin
        
        # Add members if provided
        if member_ids:
            try:
                members = User.objects.filter(id__in=member_ids).exclude(id=request.user.id)
                room.participants.add(*members)
            except Exception as e:
                # If some users don't exist, continue anyway
                pass
        
        serializer = self.get_serializer(room, context={'request': request})
        return Response({
            "success": True,
            "message": "Group room created successfully",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Get messages for a room"""
        room = self.get_object()
        if request.user not in room.participants.all():
            return Response({
                "success": False,
                "error": "You don't have access to this room"
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get messages for this room, ordered by created_at
        messages = Message.objects.filter(room=room).select_related('sender', 'room').order_by('created_at')[:100]  # Get last 100 messages
        serializer = MessageSerializer(messages, many=True, context={'request': request})
        
        # Mark messages as read (only messages sent to current user)
        Message.objects.filter(
            room=room,
            is_read=False
        ).exclude(sender=request.user).update(is_read=True)
        
        return Response({
            "success": True,
            "data": serializer.data
        })

    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Send a message to a room"""
        room = self.get_object()
        if request.user not in room.participants.all():
            return Response({
                "success": False,
                "error": "You don't have access to this room"
            }, status=status.HTTP_403_FORBIDDEN)
        
        content = request.data.get('content', '').strip()
        if not content:
            return Response({
                "success": False,
                "error": "Message content is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        message = Message.objects.create(
            room=room,
            sender=request.user,
            content=content
        )
        
        # Broadcast via WebSocket to all room participants
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to room's channel group
            async_to_sync(channel_layer.group_send)(
                f'chat_{room.id}',
                {
                    'type': 'chat_message',
                    'message': {
                        'id': message.id,
                        'content': message.content,
                        'sender_id': request.user.id,
                        'sender_username': request.user.username,
                        'room_id': room.id,
                        'created_at': message.created_at.isoformat(),
                        'is_read': message.is_read,
                    }
                }
            )
        
        serializer = MessageSerializer(message, context={'request': request})
        return Response({
            "success": True,
            "message": "Message sent successfully",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def add_members(self, request, pk=None):
        """Add members to a group room"""
        room = self.get_object()
        
        if not room.is_group:
            return Response({
                "success": False,
                "error": "Can only add members to group rooms"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if request.user not in room.participants.all():
            return Response({
                "success": False,
                "error": "You don't have access to this room"
            }, status=status.HTTP_403_FORBIDDEN)
        
        member_ids = request.data.get('member_ids', [])
        if not member_ids:
            return Response({
                "success": False,
                "error": "member_ids is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            members = User.objects.filter(id__in=member_ids).exclude(id=request.user.id)
            # Exclude users already in the room
            existing_member_ids = set(room.participants.values_list('id', flat=True))
            new_members = [m for m in members if m.id not in existing_member_ids]
            
            if new_members:
                room.participants.add(*new_members)
            
            serializer = self.get_serializer(room, context={'request': request})
            return Response({
                "success": True,
                "message": f"Added {len(new_members)} member(s) to the room",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def make_admin(self, request, pk=None):
        """Make a user an admin of the room (only current admins can do this)"""
        room = self.get_object()
        
        if not room.is_group:
            return Response({
                "success": False,
                "error": "Can only manage admins for group rooms"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not room.is_admin(request.user):
            return Response({
                "success": False,
                "error": "Only admins can make other users admin"
            }, status=status.HTTP_403_FORBIDDEN)
        
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({
                "success": False,
                "error": "user_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(id=user_id)
            if user not in room.participants.all():
                return Response({
                    "success": False,
                    "error": "User must be a participant of the room"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if room.is_admin(user):
                return Response({
                    "success": False,
                    "error": "User is already an admin"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            room.admins.add(user)
            serializer = self.get_serializer(room, context={'request': request})
            return Response({
                "success": True,
                "message": f"{user.username} is now an admin",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        """Remove a member from the room (only admins can do this)"""
        room = self.get_object()
        
        if not room.is_group:
            return Response({
                "success": False,
                "error": "Can only remove members from group rooms"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not room.is_admin(request.user):
            return Response({
                "success": False,
                "error": "Only admins can remove members"
            }, status=status.HTTP_403_FORBIDDEN)
        
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({
                "success": False,
                "error": "user_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(id=user_id)
            if user == request.user:
                return Response({
                    "success": False,
                    "error": "Cannot remove yourself from the room"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if user not in room.participants.all():
                return Response({
                    "success": False,
                    "error": "User is not a participant of the room"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            room.participants.remove(user)
            room.admins.remove(user)  # Also remove from admins if they were an admin
            
            serializer = self.get_serializer(room, context={'request': request})
            return Response({
                "success": True,
                "message": f"{user.username} has been removed from the room",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)


class ChatUserListView(APIView):
    """Get users for chat - all users (first 20)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get all users for chat (first 20)"""
        # Mark current user as online when they visit chat
        from django.core.cache import cache
        cache.set(f'user_online_{request.user.id}', True, timeout=300)  # 5 minutes
        
        # Get all users except current user, limit to 20
        all_users = User.objects.exclude(id=request.user.id).select_related('profile')[:20]
        
        serializer = UserSerializer(all_users, many=True, context={'request': request})
        return Response({
            "success": True,
            "data": serializer.data
        })


class ChatUserSearchView(APIView):
    """Search users for chat"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Search users by username or email"""
        query = request.query_params.get('q', '').strip()
        
        if not query or len(query) < 2:
            return Response({
                "success": False,
                "error": "Search query must be at least 2 characters"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        users = User.objects.filter(
            Q(username__icontains=query) | 
            Q(email__icontains=query)
        ).exclude(id=request.user.id)[:20]  # Limit to 20 results
        
        serializer = UserSerializer(users, many=True, context={'request': request})
        return Response({
            "success": True,
            "data": serializer.data
        })


""" Direct Messaging Views """
class SendDirectMessageView(APIView):
    """Send a direct message to a user"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        receiver_id = request.data.get('receiver_id')
        content = request.data.get('content', '').strip()
        
        if not receiver_id:
            return Response({
                "success": False,
                "error": "receiver_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not content:
            return Response({
                "success": False,
                "error": "Message content is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            receiver = User.objects.get(id=receiver_id)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "Receiver user not found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        if receiver == request.user:
            return Response({
                "success": False,
                "error": "Cannot send message to yourself"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create direct message
        message = Message.objects.create(
            sender=request.user,
            receiver=receiver,
            content=content
        )
        
        # Broadcast via WebSocket to both sender and receiver
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to receiver's personal channel
            async_to_sync(channel_layer.group_send)(
                f'user_{receiver.id}',
                {
                    'type': 'direct_message',
                    'message': {
                        'id': message.id,
                        'content': message.content,
                        'sender_id': request.user.id,
                        'sender_username': request.user.username,
                        'receiver_id': receiver.id,
                        'created_at': message.created_at.isoformat(),
                        'is_read': message.is_read,
                    }
                }
            )
            # Also send to sender's channel for confirmation
            async_to_sync(channel_layer.group_send)(
                f'user_{request.user.id}',
                {
                    'type': 'direct_message',
                    'message': {
                        'id': message.id,
                        'content': message.content,
                        'sender_id': request.user.id,
                        'sender_username': request.user.username,
                        'receiver_id': receiver.id,
                        'created_at': message.created_at.isoformat(),
                        'is_read': message.is_read,
                    }
                }
            )
        
        serializer = MessageSerializer(message, context={'request': request})
        return Response({
            "success": True,
            "message": "Message sent successfully",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)


class GetConversationView(APIView):
    """Get conversation messages between current user and another user"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response({
                "success": False,
                "error": "user_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            other_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get all messages between current user and other user
        messages = Message.objects.filter(
            Q(sender=request.user, receiver=other_user) |
            Q(sender=other_user, receiver=request.user)
        ).select_related('sender', 'receiver').order_by('created_at')[:100]  # Get last 100 messages
        
        # Mark messages as read (only messages sent to current user)
        Message.objects.filter(
            sender=other_user,
            receiver=request.user,
            is_read=False
        ).update(is_read=True)
        
        serializer = MessageSerializer(messages, many=True, context={'request': request})
        
        # Include user info with last_seen
        user_serializer = UserSerializer(other_user, context={'request': request})
        
        return Response({
            "success": True,
            "data": serializer.data,
            "user": user_serializer.data  # Include user info with online status and last_seen
        })


class GetConversationsListView(APIView):
    """Get list of users the current user has conversations with"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Mark current user as online when they visit chat
        from django.core.cache import cache
        cache.set(f'user_online_{request.user.id}', True, timeout=300)  # 5 minutes
        # Get all users the current user has sent or received messages from
        sent_to = Message.objects.filter(sender=request.user).values_list('receiver_id', flat=True).distinct()
        received_from = Message.objects.filter(receiver=request.user).values_list('sender_id', flat=True).distinct()
        
        # Combine and get unique user IDs
        user_ids = set(list(sent_to) + list(received_from))
        
        # Get the latest message for each conversation
        conversations = []
        for user_id in user_ids:
            try:
                other_user = User.objects.get(id=user_id)
                last_message = Message.objects.filter(
                    Q(sender=request.user, receiver=other_user) |
                    Q(sender=other_user, receiver=request.user)
                ).select_related('sender', 'receiver').order_by('-created_at').first()
                
                unread_count = Message.objects.filter(
                    sender=other_user,
                    receiver=request.user,
                    is_read=False
                ).count()
                
                conversations.append({
                    'user': UserSerializer(other_user, context={'request': request}).data,
                    'last_message': MessageSerializer(last_message, context={'request': request}).data if last_message else None,
                    'unread_count': unread_count,
                    'last_message_time': last_message.created_at.isoformat() if last_message else None
                })
            except User.DoesNotExist:
                continue
        
        # Sort by last message time (most recent first)
        conversations.sort(key=lambda x: x['last_message_time'] or '', reverse=True)
        
        return Response({
            "success": True,
            "data": conversations
        })