from django.db import models
from django.db.models import Q
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


class BlockedUser(models.Model):
    """Model to track blocked users in chat"""
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_users')
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by_users')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('blocker', 'blocked')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['blocker', '-created_at']),
            models.Index(fields=['blocked', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked.username}"


class UserReport(models.Model):
    """Model to track user reports in chat"""
    REPORT_REASONS = [
        ('spam', 'Spam'),
        ('harassment', 'Harassment'),
        ('inappropriate_content', 'Inappropriate Content'),
        ('fake_account', 'Fake Account'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]
    
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')
    reported_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_received')
    reason = models.CharField(max_length=50, choices=REPORT_REASONS)
    description = models.TextField(blank=True, help_text='Additional details about the report')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reports_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True, help_text='Admin notes about the report')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['reported_user', 'status', '-created_at']),
            models.Index(fields=['reporter', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.reporter.username} reported {self.reported_user.username} - {self.reason}"


class MessageRequest(models.Model):
    """Model to track message requests from unknown users"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_message_requests')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_message_requests')
    content = models.TextField(help_text='Initial message content')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['receiver', 'status', '-created_at']),
            models.Index(fields=['sender', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username}: {self.status}"


class AcceptedMessage(models.Model):
    """Model to track accepted message relationships (users who can message each other)"""
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accepted_contacts_1')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accepted_contacts_2')
    accepted_at = models.DateTimeField(auto_now_add=True)
    accepted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_acceptances', null=True)
    
    class Meta:
        unique_together = ('user1', 'user2')
        ordering = ['-accepted_at']
        indexes = [
            models.Index(fields=['user1', '-accepted_at']),
            models.Index(fields=['user2', '-accepted_at']),
        ]
    
    def __str__(self):
        return f"{self.user1.username} <-> {self.user2.username}"
    
    @classmethod
    def can_message(cls, user1, user2):
        """Check if two users can message each other"""
        return cls.objects.filter(
            (Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1))
        ).exists()

""" End of Chat Models """