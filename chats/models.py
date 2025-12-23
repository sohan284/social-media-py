from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

""" Chat Models """
class Room(models.Model):
    """ Room model for Chat - supports both group and one-on-one chats """
    name = models.CharField(max_length=255, null=True, blank=True)
    participants = models.ManyToManyField(User, blank=True, related_name='chat_rooms')
    admins = models.ManyToManyField(User, blank=True, related_name='admin_rooms')
    is_group = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        if self.is_group:
            return self.name or f"Group Chat {self.id}"
        participants = list(self.participants.all()[:2])
        if len(participants) == 2:
            return f"{participants[0].username} & {participants[1].username}"
        return f"Chat {self.id}"

    def get_other_participant(self, user):
        """Get the other participant in a one-on-one chat"""
        if self.is_group:
            return None
        other = self.participants.exclude(id=user.id).first()
        return other
    
    def is_admin(self, user):
        """Check if user is an admin of this room"""
        return self.admins.filter(id=user.id).exists()

class Message(models.Model):
    """ Message model for Chat - supports both room-based and direct messages """
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='received_messages')
    content = models.TextField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['room', '-created_at']),
            models.Index(fields=['sender', '-created_at']),
            models.Index(fields=['receiver', '-created_at']),
            models.Index(fields=['sender', 'receiver', '-created_at']),  # For direct message queries
        ]

    def __str__(self):
        return f"{self.sender.username if self.sender else 'Unknown'}: {self.content[:50]}"

""" End of Chat Models """