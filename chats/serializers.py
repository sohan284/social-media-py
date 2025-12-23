from rest_framework import serializers 
from .models import Room, Message
from accounts.serializers import UserSerializer

""" Serializers for Chat """
class MessageSerializer(serializers.ModelSerializer):
    """ Serializer for Message """
    sender = UserSerializer(read_only=True)
    sender_id = serializers.IntegerField(source='sender.id', read_only=True)
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    receiver = UserSerializer(read_only=True)
    receiver_id = serializers.IntegerField(source='receiver.id', read_only=True)
    room_id = serializers.IntegerField(source='room.id', read_only=True)
    
    class Meta:
        model = Message
        fields = ['id', 'sender', 'sender_id', 'sender_username', 'receiver', 'receiver_id', 'room_id', 'content', 'is_read', 'created_at']
        read_only_fields = ['sender', 'receiver', 'created_at']

class RoomSerializer(serializers.ModelSerializer):
    """ Serializer for Room """
    participants = UserSerializer(many=True, read_only=True)
    admins = UserSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()
    
    class Meta:
        model = Room
        fields = ['id', 'name', 'participants', 'admins', 'is_group', 'last_message', 'unread_count', 'other_participant', 'is_admin', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_last_message(self, obj):
        last_msg = obj.messages.last()
        if last_msg:
            return MessageSerializer(last_msg).data
        return None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
        return 0

    def get_other_participant(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated and not obj.is_group:
            other = obj.get_other_participant(request.user)
            if other:
                return UserSerializer(other).data
        return None
    
    def get_is_admin(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.is_admin(request.user)
        return False

""" End of Serializers for Chat """