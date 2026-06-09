from django_filters import FilterSet, ChoiceFilter, CharFilter
from django.utils.translation import gettext_lazy as _

from .models import Notification


class NotificationFilter(FilterSet):
    status = ChoiceFilter(
        choices=Notification.NotificationStatus.choices,
        field_name=_('status')
    )
    notification_type = ChoiceFilter(
        choices=Notification.NotificationType.choices,
        field_name=_('notification type')
    )
    is_unread = CharFilter(method='filter_unread')

    class Meta:
        model = Notification
        fields = ('status', 'notification_type')

    def get_filter_unread(self, queryset, name, value):
        if value.lower() == 'true':
            return queryset.filter(status='unread')
        return queryset