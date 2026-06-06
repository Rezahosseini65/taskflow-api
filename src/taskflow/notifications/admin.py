from django.contrib import admin
from django.utils.html import format_html
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'recipient', 'notification_type', 'title', 'status', 'created_at']
    list_filter = ['notification_type', 'status']
    search_fields = ['recipient__email', 'title']
    list_editable = ['status']
    readonly_fields = ['created_at']

    @admin.display(description='نوع')
    def notification_type(self, obj):
        colors = {
            'join_request': '🟠',
            'join_approved': '🟢',
            'join_rejected': '🔴',
            'invitation': '🔵',
            'system': '⚪',
        }
        return f"{colors.get(obj.notification_type, '⚪')} {obj.get_notification_type_display()}"

    @admin.display(description='وضعیت')
    def status(self, obj):
        icons = {'unread': '🔴', 'read': '✅', 'archived': '📦'}
        return f"{icons.get(obj.status, '')} {obj.get_status_display()}"