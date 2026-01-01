from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(Post)
admin.site.register(Like)
admin.site.register(Comment)
admin.site.register(Share)
admin.site.register(Follow)
admin.site.register(Notification)
admin.site.register(PostView)


@admin.register(PostReport)
class PostReportAdmin(admin.ModelAdmin):
    """Admin interface for Post Reports"""
    list_display = [
        'id', 'post_title', 'reporter_name', 'post_author', 
        'reason', 'status', 'created_at', 'reviewed_by_name', 'reviewed_at'
    ]
    list_filter = ['status', 'reason', 'created_at', 'reviewed_at']
    search_fields = [
        'post__title', 'reporter__username', 'post__user__username',
        'reason', 'description'
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = (
        ('Report Information', {
            'fields': ('reporter', 'post', 'reason', 'description', 'status')
        }),
        ('Review Information', {
            'fields': ('reviewed_by', 'reviewed_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def post_title(self, obj):
        return obj.post.title if obj.post else "N/A"
    post_title.short_description = 'Post Title'
    post_title.admin_order_field = 'post__title'
    
    def reporter_name(self, obj):
        return obj.reporter.username if obj.reporter else "N/A"
    reporter_name.short_description = 'Reporter'
    reporter_name.admin_order_field = 'reporter__username'
    
    def post_author(self, obj):
        return obj.post.user.username if obj.post and obj.post.user else "N/A"
    post_author.short_description = 'Post Author'
    post_author.admin_order_field = 'post__user__username'
    
    def reviewed_by_name(self, obj):
        return obj.reviewed_by.username if obj.reviewed_by else "Not Reviewed"
    reviewed_by_name.short_description = 'Reviewed By'
    reviewed_by_name.admin_order_field = 'reviewed_by__username'
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('reporter', 'post', 'post__user', 'reviewed_by')
    
    actions = ['mark_as_reviewed', 'mark_as_resolved', 'mark_as_dismissed']
    
    def mark_as_reviewed(self, request, queryset):
        """Mark selected reports as reviewed"""
        from django.utils import timezone
        updated = queryset.update(
            status='reviewed',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{updated} report(s) marked as reviewed.')
    mark_as_reviewed.short_description = "Mark selected reports as reviewed"
    
    def mark_as_resolved(self, request, queryset):
        """Mark selected reports as resolved"""
        from django.utils import timezone
        updated = queryset.update(
            status='resolved',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{updated} report(s) marked as resolved.')
    mark_as_resolved.short_description = "Mark selected reports as resolved"
    
    def mark_as_dismissed(self, request, queryset):
        """Mark selected reports as dismissed"""
        from django.utils import timezone
        updated = queryset.update(
            status='dismissed',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{updated} report(s) marked as dismissed.')
    mark_as_dismissed.short_description = "Mark selected reports as dismissed"