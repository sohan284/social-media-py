from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Profile, Contact

class CustomUserAdmin(UserAdmin):
    model = User

    list_display = ('username', 'email', 'role', 'is_staff', 'is_active', 'email_verified')
    list_filter = ('role', 'is_staff', 'is_active', 'email_verified')

    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('role', 'email_verified', 'verification_code', 'is_oauth_user', 'username_set')}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('role', 'email_verified', 'is_oauth_user', 'username_set')}),
    )

    search_fields = ('email', 'username')
    ordering = ('email',)

admin.site.register(User, CustomUserAdmin)
admin.site.register(Profile)

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'subject', 'created_at', 'is_read', 'read_by')
    list_filter = ('is_read', 'created_at')
    search_fields = ('first_name', 'last_name', 'email', 'subject', 'message')
    readonly_fields = ('created_at', 'read_at', 'read_by')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Contact Information', {
            'fields': ('first_name', 'last_name', 'email', 'subject', 'message')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at', 'read_by')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )
