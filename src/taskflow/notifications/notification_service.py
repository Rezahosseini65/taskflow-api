import logging

from django.core.cache import cache
from django.utils import timezone

from .models import Notification
from taskflow.companies.models import Membership

logger = logging.getLogger(__name__)

def invalidate_notification_cache(user_ids):
    """
    Invalidate notification cache for one or more users.
    """

    if not isinstance(user_ids, (list, tuple, set)):
        user_ids = [user_ids]

    for user_id in user_ids:
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"notification_list_user_{user_id}_*")
        else:
            cache.delete(f"notification_list_user_{user_id}")

        logger.debug(
            f"Notification cache invalidated for user {user_id}"
        )

def mark_notification_as_read(
    *,
    recipient,
    invitation,
    notification_type,
    metadata=None,
):
    return Notification.objects.filter(
        recipient=recipient,
        invitation=invitation,
        notification_type=notification_type,
        status=Notification.NotificationStatus.UNREAD,
    ).update(
        status=Notification.NotificationStatus.READ,
        read_at=timezone.now(),
        metadata=metadata or {},
    )

def create_notification(
    *,
    recipient,
    sender,
    notification_type,
    title,
    message,
    action_url,
    invitation,
    company,
    metadata=None,
):
    notification = Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type=notification_type,
        title=title,
        message=message,
        action_url=action_url,
        invitation=invitation,
        company=company,
        status=Notification.NotificationStatus.UNREAD,
        metadata=metadata or {},
    )

    invalidate_notification_cache(recipient.id)

    return notification

def notify_company_admins(
    *,
    company,
    sender,
    invitation,
    notification_type,
    title,
    message,
    action_url,
    metadata=None,
):
    admins = get_admins(company)

    if not admins.exists():
            admins = Membership.objects.filter(
            company=company,
            role=Membership.RoleChoices.OWNER
        ).select_related('user')

    if not admins.exists():
        logger.warning(
            f"No admins found for company {company.id}"
        )
        return 0

    notifications = []

    admin_ids = []

    for admin in admins:
        notification = Notification(
                recipient=admin.user,
                sender=sender,
                notification_type=notification_type,
                title=title,
                message=message,
                action_url=action_url,
                invitation=invitation,
                company=company,
                status=Notification.NotificationStatus.UNREAD,
                metadata=metadata or {},
        )
        notifications.append(notification)
        admin_ids.append(admin.user.id)

    if notifications:
        Notification.objects.bulk_create(notifications)

    invalidate_notification_cache(admin_ids)

    return len(notifications)

def get_admins(company):
    return Membership.objects.filter(
        company=company,
        role__in=[
            Membership.RoleChoices.OWNER,
            Membership.RoleChoices.ADMIN,
        ],
    ).select_related("user")