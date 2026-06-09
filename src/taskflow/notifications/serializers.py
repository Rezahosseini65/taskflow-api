from rest_framework import serializers

from .models import Notification

class NotificationListSerializer(serializers.ModelSerializer):
    sender_email = serializers.EmailField(
        source='sender.email',
        read_only=True,
        default='System'
    )
    notification_type_display = serializers.CharField(
        source='get_notification_type_display',
        read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )

    class Meta:
        model = Notification
        fields = (
            'id', 'title', 'message', 'sender_email',
            'notification_type_display', 'status_display',
            'created_at', 'time_ago', 'is_read', 'action_url',
        )
        read_only_fields = (
            'id', 'title', 'message', 'notification_type',
            'status', 'created_at', 'action_url', 'is_read', 'time_ago'
        )



