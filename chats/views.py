from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, Max, Count
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Room, Message, BlockedUser, UserReport
from .serializers import (
    RoomSerializer, MessageSerializer, BlockedUserSerializer, 
    UserReportSerializer, CreateUserReportSerializer
)
from accounts.serializers import UserSerializer
from accounts.permissions import IsAdmin
from post.models import Follow

User = get_user_model()

""" Viewset for Chat """
class RoomViewSet(viewsets.ModelViewSet):
    """ Viewset for Room """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RoomSerializer

    def get_queryset(self):
        """Get rooms where current user is a participant, excluding blocked users"""
        # Get IDs of users blocked by current user
        blocked_user_ids = BlockedUser.objects.filter(
            blocker=self.request.user
        ).values_list('blocked_id', flat=True)
        
        # Get rooms where current user is a participant
        rooms = Room.objects.filter(participants=self.request.user).annotate(
            last_message_time=Max('messages__created_at')
        ).order_by('-last_message_time', '-updated_at').distinct()
        
        # For one-on-one chats, exclude rooms with blocked users
        if blocked_user_ids:
            rooms = rooms.exclude(
                is_group=False,
                participants__id__in=blocked_user_ids
            )
        
        return rooms

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
            
            # Check if user is blocked
            if BlockedUser.objects.filter(blocker=request.user, blocked=other_user).exists():
                return Response({
                    "success": False,
                    "error": "You have blocked this user"
                }, status=status.HTTP_403_FORBIDDEN)
            
            if BlockedUser.objects.filter(blocker=other_user, blocked=request.user).exists():
                return Response({
                    "success": False,
                    "error": "This user has blocked you"
                }, status=status.HTTP_403_FORBIDDEN)
            
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
        
        # Check if sender is blocked by any participant (for one-on-one chats)
        if not room.is_group:
            other_participant = room.get_other_participant(request.user)
            if other_participant:
                if BlockedUser.objects.filter(blocker=other_participant, blocked=request.user).exists():
                    return Response({
                        "success": False,
                        "error": "This user has blocked you"
                    }, status=status.HTTP_403_FORBIDDEN)
        
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

    @action(detail=True, methods=['patch'])
    def update_message(self, request, pk=None):
        """Update a message in a room (only sender can update)"""
        room = self.get_object()
        if request.user not in room.participants.all():
            return Response({
                "success": False,
                "error": "You don't have access to this room"
            }, status=status.HTTP_403_FORBIDDEN)
        
        message_id = request.data.get('message_id')
        content = request.data.get('content', '').strip()
        
        if not message_id:
            return Response({
                "success": False,
                "error": "message_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not content:
            return Response({
                "success": False,
                "error": "Message content is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            message = Message.objects.get(id=message_id, room=room)
        except Message.DoesNotExist:
            return Response({
                "success": False,
                "error": "Message not found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Only sender can update their message
        if message.sender != request.user:
            return Response({
                "success": False,
                "error": "You can only edit your own messages"
            }, status=status.HTTP_403_FORBIDDEN)
        
        message.content = content
        message.save()
        
        # Broadcast update via WebSocket
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'chat_{room.id}',
                {
                    'type': 'message_updated',
                    'message': {
                        'id': message.id,
                        'content': message.content,
                        'room_id': room.id,
                    }
                }
            )
        
        serializer = MessageSerializer(message, context={'request': request})
        return Response({
            "success": True,
            "message": "Message updated successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['delete'])
    def delete_message(self, request, pk=None):
        """Delete a message from a room (only sender can delete)"""
        room = self.get_object()
        if request.user not in room.participants.all():
            return Response({
                "success": False,
                "error": "You don't have access to this room"
            }, status=status.HTTP_403_FORBIDDEN)
        
        message_id = request.query_params.get('message_id') or request.data.get('message_id')
        
        if not message_id:
            return Response({
                "success": False,
                "error": "message_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            message = Message.objects.get(id=message_id, room=room)
        except Message.DoesNotExist:
            return Response({
                "success": False,
                "error": "Message not found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Only sender can delete their message
        if message.sender != request.user:
            return Response({
                "success": False,
                "error": "You can only delete your own messages"
            }, status=status.HTTP_403_FORBIDDEN)
        
        message_id_for_ws = message.id
        message.delete()
        
        # Broadcast deletion via WebSocket
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'chat_{room.id}',
                {
                    'type': 'message_deleted',
                    'message_id': message_id_for_ws,
                    'room_id': room.id,
                }
            )
        
        return Response({
            "success": True,
            "message": "Message deleted successfully"
        }, status=status.HTTP_200_OK)

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
        
        # Get IDs of users blocked by current user
        blocked_user_ids = BlockedUser.objects.filter(
            blocker=request.user
        ).values_list('blocked_id', flat=True)
        
        # Get all users except current user and blocked users, limit to 20
        all_users = User.objects.exclude(id=request.user.id).select_related('profile')
        if blocked_user_ids:
            all_users = all_users.exclude(id__in=blocked_user_ids)
        all_users = all_users[:20]
        
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
        
        # Get IDs of users blocked by current user
        blocked_user_ids = BlockedUser.objects.filter(
            blocker=request.user
        ).values_list('blocked_id', flat=True)
        
        users = User.objects.filter(
            Q(username__icontains=query) | 
            Q(email__icontains=query)
        ).exclude(id=request.user.id)
        
        if blocked_user_ids:
            users = users.exclude(id__in=blocked_user_ids)
        
        users = users[:20]  # Limit to 20 results
        
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
        
        # Check if user is blocked
        if BlockedUser.objects.filter(blocker=request.user, blocked=receiver).exists():
            return Response({
                "success": False,
                "error": "You have blocked this user"
            }, status=status.HTTP_403_FORBIDDEN)
        
        if BlockedUser.objects.filter(blocker=receiver, blocked=request.user).exists():
            return Response({
                "success": False,
                "error": "This user has blocked you"
            }, status=status.HTTP_403_FORBIDDEN)
        
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


class UpdateDirectMessageView(APIView):
    """Update a direct message (only sender can update)"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        message_id = request.data.get('message_id')
        content = request.data.get('content', '').strip()
        
        if not message_id:
            return Response({
                "success": False,
                "error": "message_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not content:
            return Response({
                "success": False,
                "error": "Message content is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            message = Message.objects.get(id=message_id, sender=request.user)
        except Message.DoesNotExist:
            return Response({
                "success": False,
                "error": "Message not found or you don't have permission to edit it"
            }, status=status.HTTP_404_NOT_FOUND)
        
        message.content = content
        message.save()
        
        # Broadcast update via WebSocket
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to receiver
            if message.receiver:
                async_to_sync(channel_layer.group_send)(
                    f'user_{message.receiver.id}',
                    {
                        'type': 'message_updated',
                        'message': {
                            'id': message.id,
                            'content': message.content,
                            'sender_id': request.user.id,
                            'receiver_id': message.receiver.id,
                        }
                    }
                )
            # Send to sender
            async_to_sync(channel_layer.group_send)(
                f'user_{request.user.id}',
                {
                    'type': 'message_updated',
                    'message': {
                        'id': message.id,
                        'content': message.content,
                        'sender_id': request.user.id,
                        'receiver_id': message.receiver.id if message.receiver else None,
                    }
                }
            )
        
        serializer = MessageSerializer(message, context={'request': request})
        return Response({
            "success": True,
            "message": "Message updated successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class DeleteDirectMessageView(APIView):
    """Delete a direct message (only sender can delete)"""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        message_id = request.query_params.get('message_id') or request.data.get('message_id')
        
        if not message_id:
            return Response({
                "success": False,
                "error": "message_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            message = Message.objects.get(id=message_id, sender=request.user)
        except Message.DoesNotExist:
            return Response({
                "success": False,
                "error": "Message not found or you don't have permission to delete it"
            }, status=status.HTTP_404_NOT_FOUND)
        
        receiver_id = message.receiver.id if message.receiver else None
        message_id_for_ws = message.id
        message.delete()
        
        # Broadcast deletion via WebSocket
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to receiver
            if receiver_id:
                async_to_sync(channel_layer.group_send)(
                    f'user_{receiver_id}',
                    {
                        'type': 'message_deleted',
                        'message_id': message_id_for_ws,
                        'sender_id': request.user.id,
                        'receiver_id': receiver_id,
                    }
                )
            # Send to sender
            async_to_sync(channel_layer.group_send)(
                f'user_{request.user.id}',
                {
                    'type': 'message_deleted',
                    'message_id': message_id_for_ws,
                    'sender_id': request.user.id,
                    'receiver_id': receiver_id,
                }
            )
        
        return Response({
            "success": True,
            "message": "Message deleted successfully"
        }, status=status.HTTP_200_OK)


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
        
        # Check block status (but still allow viewing messages)
        i_blocked_them = BlockedUser.objects.filter(blocker=request.user, blocked=other_user).exists()
        they_blocked_me = BlockedUser.objects.filter(blocker=other_user, blocked=request.user).exists()
        
        # Get all messages between current user and other user (even if blocked)
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
        
        # Include user info with last_seen and block status
        user_serializer = UserSerializer(other_user, context={'request': request})
        
        return Response({
            "success": True,
            "data": serializer.data,
            "user": user_serializer.data,  # Include user info with online status and last_seen
            "block_status": {
                "i_blocked_them": i_blocked_them,
                "they_blocked_me": they_blocked_me,
            }
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
        
        # Combine and get unique user IDs (include blocked users so they appear in list)
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
                
                # Check block status
                i_blocked_them = BlockedUser.objects.filter(blocker=request.user, blocked=other_user).exists()
                they_blocked_me = BlockedUser.objects.filter(blocker=other_user, blocked=request.user).exists()
                
                conversations.append({
                    'user': UserSerializer(other_user, context={'request': request}).data,
                    'last_message': MessageSerializer(last_message, context={'request': request}).data if last_message else None,
                    'unread_count': unread_count,
                    'last_message_time': last_message.created_at.isoformat() if last_message else None,
                    'i_blocked_them': i_blocked_them,
                    'they_blocked_me': they_blocked_me,
                })
            except User.DoesNotExist:
                continue
        
        # Sort by last message time (most recent first)
        conversations.sort(key=lambda x: x['last_message_time'] or '', reverse=True)
        
        return Response({
            "success": True,
            "data": conversations
        })


""" Block and Report Views """
class BlockUserView(APIView):
    """Block a user"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        user_id = request.data.get('user_id')
        
        if not user_id:
            return Response({
                "success": False,
                "error": "user_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user_to_block = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({
                "success": False,
                "error": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        if user_to_block == request.user:
            return Response({
                "success": False,
                "error": "You cannot block yourself"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if already blocked
        blocked, created = BlockedUser.objects.get_or_create(
            blocker=request.user,
            blocked=user_to_block
        )
        
        if not created:
            return Response({
                "success": False,
                "error": "User is already blocked"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = BlockedUserSerializer(blocked, context={'request': request})
        return Response({
            "success": True,
            "message": f"You have blocked {user_to_block.username}",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)


class UnblockUserView(APIView):
    """Unblock a user"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        user_id = request.data.get('user_id')
        
        if not user_id:
            return Response({
                "success": False,
                "error": "user_id is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            blocked_user = BlockedUser.objects.get(
                blocker=request.user,
                blocked_id=user_id
            )
        except BlockedUser.DoesNotExist:
            return Response({
                "success": False,
                "error": "User is not blocked"
            }, status=status.HTTP_404_NOT_FOUND)
        
        username = blocked_user.blocked.username
        blocked_user.delete()
        
        return Response({
            "success": True,
            "message": f"You have unblocked {username}"
        }, status=status.HTTP_200_OK)


class BlockedUsersListView(APIView):
    """Get list of blocked users"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        blocked_users = BlockedUser.objects.filter(blocker=request.user).select_related('blocked')
        serializer = BlockedUserSerializer(blocked_users, many=True, context={'request': request})
        
        return Response({
            "success": True,
            "data": serializer.data
        })


class ReportUserView(APIView):
    """Report a user"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = CreateUserReportSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            report = serializer.save(reporter=request.user)
            report_serializer = UserReportSerializer(report, context={'request': request})
            
            return Response({
                "success": True,
                "message": "User has been reported. Our team will review this report.",
                "data": report_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            "success": False,
            "error": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class UserReportsListView(APIView):
    """Get list of user reports (admin only)"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    
    def get(self, request):
        status_filter = request.query_params.get('status', None)
        queryset = UserReport.objects.all().select_related('reporter', 'reported_user', 'reviewed_by')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        queryset = queryset.order_by('-created_at')
        serializer = UserReportSerializer(queryset, many=True, context={'request': request})
        
        return Response({
            "success": True,
            "data": serializer.data
        })


class UpdateReportStatusView(APIView):
    """Update report status (admin only)"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    
    def patch(self, request, report_id):
        try:
            report = UserReport.objects.get(id=report_id)
        except UserReport.DoesNotExist:
            return Response({
                "success": False,
                "error": "Report not found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        new_status = request.data.get('status')
        admin_notes = request.data.get('admin_notes', '')
        
        if new_status and new_status in dict(UserReport.STATUS_CHOICES):
            report.status = new_status
            report.reviewed_by = request.user
            report.reviewed_at = timezone.now()
            if admin_notes:
                report.admin_notes = admin_notes
            report.save()
            
            serializer = UserReportSerializer(report, context={'request': request})
            return Response({
                "success": True,
                "message": "Report status updated",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({
            "success": False,
            "error": "Invalid status"
        }, status=status.HTTP_400_BAD_REQUEST)


class DeleteUserReportView(APIView):
    """Delete a user report (admin only)"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    
    def delete(self, request, report_id):
        try:
            report = UserReport.objects.get(id=report_id)
            report.delete()
            return Response({
                "success": True,
                "message": "Report deleted successfully"
            }, status=status.HTTP_200_OK)
        except UserReport.DoesNotExist:
            return Response({
                "success": False,
                "error": "Report not found"
            }, status=status.HTTP_404_NOT_FOUND)


class AdminAllConversationsView(APIView):
    """Get all conversations (direct and room) for admin panel"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    
    def get(self, request):
        """Get all conversations - both direct messages and room messages with pagination"""
        try:
            # Get pagination parameters
            page = int(request.query_params.get('page', 1))
            limit = int(request.query_params.get('limit', 10))
            
            # Get filter parameters
            type_filter = request.query_params.get('type', None)
            search_query = request.query_params.get('search', None)
            
            # Validate pagination parameters
            if page < 1:
                page = 1
            if limit < 1:
                limit = 10
            if limit > 100:
                limit = 100  # Max limit
            
            # Get all direct message conversations
            # Get unique pairs of users who have exchanged messages
            direct_conversations = []
            user_pairs = Message.objects.filter(
                room__isnull=True
            ).exclude(
                sender__isnull=True
            ).exclude(
                receiver__isnull=True
            ).values_list('sender_id', 'receiver_id').distinct()
            
            # Process each user pair
            processed_pairs = set()
            for sender_id, receiver_id in user_pairs:
                # Create a consistent key for the pair (smaller_id, larger_id)
                pair_key = tuple(sorted([sender_id, receiver_id]))
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)
                
                user1_id, user2_id = pair_key
                try:
                    user1 = User.objects.get(id=user1_id)
                    user2 = User.objects.get(id=user2_id)
                    
                    # Get last message between these users
                    last_message = Message.objects.filter(
                        Q(sender=user1, receiver=user2) | Q(sender=user2, receiver=user1),
                        room__isnull=True
                    ).select_related('sender', 'receiver').order_by('-created_at').first()
                    
                    # Get message count
                    message_count = Message.objects.filter(
                        Q(sender=user1, receiver=user2) | Q(sender=user2, receiver=user1),
                        room__isnull=True
                    ).count()
                    
                    # Format created_at safely
                    created_at_str = None
                    if last_message and last_message.created_at:
                        created_at_str = last_message.created_at.isoformat()
                    
                    direct_conversations.append({
                        'id': f'direct_{user1_id}_{user2_id}',
                        'type': 'direct',
                        'user1': UserSerializer(user1, context={'request': request}).data,
                        'user2': UserSerializer(user2, context={'request': request}).data,
                        'last_message': MessageSerializer(last_message, context={'request': request}).data if last_message else None,
                        'message_count': message_count,
                        'created_at': created_at_str,
                    })
                except User.DoesNotExist:
                    continue
                except Exception as e:
                    # Log error but continue processing
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error processing direct conversation pair {pair_key}: {str(e)}")
                    continue
            
            # Get all room conversations
            rooms = Room.objects.all().annotate(
                message_count=Count('messages'),
                last_message_time=Max('messages__created_at')
            ).prefetch_related('participants', 'admins')
            
            # Order by last_message_time (nulls last) and created_at
            rooms = rooms.order_by('-last_message_time', '-created_at')
            
            room_conversations = []
            for room in rooms:
                try:
                    last_message = room.messages.select_related('sender').order_by('-created_at').first()
                    
                    # Format created_at safely
                    created_at_str = None
                    if last_message and last_message.created_at:
                        created_at_str = last_message.created_at.isoformat()
                    elif room.created_at:
                        created_at_str = room.created_at.isoformat()
                    
                    room_conversations.append({
                        'id': f'room_{room.id}',
                        'type': 'room',
                        'room_id': room.id,
                        'name': room.name,
                        'is_group': room.is_group,
                        'participants': UserSerializer(room.participants.all(), many=True, context={'request': request}).data,
                        'admins': UserSerializer(room.admins.all(), many=True, context={'request': request}).data,
                        'last_message': MessageSerializer(last_message, context={'request': request}).data if last_message else None,
                        'message_count': room.message_count or 0,
                        'created_at': created_at_str,
                    })
                except Exception as e:
                    # Log error but continue processing
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error processing room {room.id}: {str(e)}")
                    continue
            
            # Combine and sort by last message time
            all_conversations = direct_conversations + room_conversations
            all_conversations.sort(key=lambda x: x.get('created_at') or '', reverse=True)
            
            # Apply type filter
            if type_filter and type_filter != 'all':
                all_conversations = [c for c in all_conversations if c.get('type') == type_filter]
            
            # Apply search filter
            if search_query:
                search_query = search_query.strip().lower()
                if search_query:
                    filtered_conversations = []
                    for conv in all_conversations:
                        if conv.get('type') == 'direct':
                            user1 = conv.get('user1', {})
                            user2 = conv.get('user2', {})
                            user1_name = (user1.get('display_name') or user1.get('username') or '').lower()
                            user2_name = (user2.get('display_name') or user2.get('username') or '').lower()
                            user1_email = (user1.get('email') or '').lower()
                            user2_email = (user2.get('email') or '').lower()
                            if (search_query in user1_name or search_query in user2_name or 
                                search_query in user1_email or search_query in user2_email):
                                filtered_conversations.append(conv)
                        else:  # room
                            room_name = (conv.get('name') or '').lower()
                            participants = conv.get('participants', [])
                            participant_names = [
                                (p.get('display_name') or p.get('username') or '').lower()
                                for p in participants
                            ]
                            if (search_query in room_name or 
                                any(search_query in name for name in participant_names)):
                                filtered_conversations.append(conv)
                    all_conversations = filtered_conversations
            
            # Apply pagination
            total_count = len(all_conversations)
            start_index = (page - 1) * limit
            end_index = start_index + limit
            paginated_conversations = all_conversations[start_index:end_index]
            
            # Calculate pagination info
            total_pages = (total_count + limit - 1) // limit  # Ceiling division
            has_next = page < total_pages
            has_previous = page > 1
            next_page = page + 1 if has_next else None
            previous_page = page - 1 if has_previous else None
            
            # Build next and previous URLs
            base_url = request.build_absolute_uri(request.path)
            next_url = None
            previous_url = None
            
            if next_page:
                next_url = f"{base_url}?page={next_page}&limit={limit}"
            if previous_page:
                previous_url = f"{base_url}?page={previous_page}&limit={limit}"
            
            return Response({
                "count": total_count,
                "next": next_url,
                "previous": previous_url,
                "results": {
                    "success": True,
                    "data": paginated_conversations
                }
            })
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in AdminAllConversationsView: {str(e)}")
            return Response({
                "success": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminGetConversationMessagesView(APIView):
    """Get conversation messages for admin panel - can view any conversation"""
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    
    def get(self, request):
        """Get messages for a conversation (direct or room) - admin only"""
        conversation_type = request.query_params.get('type')  # 'direct' or 'room'
        user1_id = request.query_params.get('user1_id')
        user2_id = request.query_params.get('user2_id')
        room_id = request.query_params.get('room_id')
        
        if conversation_type == 'direct':
            if not user1_id or not user2_id:
                return Response({
                    "success": False,
                    "error": "user1_id and user2_id are required for direct conversations"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                user1 = User.objects.get(id=user1_id)
                user2 = User.objects.get(id=user2_id)
            except User.DoesNotExist:
                return Response({
                    "success": False,
                    "error": "One or both users not found"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get all messages between these two users
            messages = Message.objects.filter(
                Q(sender=user1, receiver=user2) | Q(sender=user2, receiver=user1),
                room__isnull=True
            ).select_related('sender', 'receiver').order_by('created_at')
            
            serializer = MessageSerializer(messages, many=True, context={'request': request})
            
            return Response({
                "success": True,
                "data": serializer.data
            })
        
        elif conversation_type == 'room':
            if not room_id:
                return Response({
                    "success": False,
                    "error": "room_id is required for room conversations"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                room = Room.objects.get(id=room_id)
            except Room.DoesNotExist:
                return Response({
                    "success": False,
                    "error": "Room not found"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get all messages in this room
            messages = Message.objects.filter(
                room=room
            ).select_related('sender', 'room').order_by('created_at')
            
            serializer = MessageSerializer(messages, many=True, context={'request': request})
            
            return Response({
                "success": True,
                "data": serializer.data
            })
        
        else:
            return Response({
                "success": False,
                "error": "type must be 'direct' or 'room'"
            }, status=status.HTTP_400_BAD_REQUEST)