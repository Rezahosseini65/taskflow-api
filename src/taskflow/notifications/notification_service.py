import logging

from django.core.cache import cache
from django.utils import timezone

from taskflow.companies.models import Membership

from .models import Notification
from taskflow.companies.services import get_admins

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
            "Notification cache invalidated for user %s",
            user_id,
        )


def _notification_data(
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
    """
    Build notification payload.
    """
    return {
        "recipient": recipient,
        "sender": sender,
        "notification_type": notification_type,
        "title": title,
        "message": message,
        "action_url": action_url,
        "invitation": invitation,
        "company": company,
        "status": Notification.NotificationStatus.UNREAD,
        "metadata": metadata or {},
    }


def _get_company_admins(company):
    """
    Return admins.
    Fallback to owners if no admin exists.
    """
    admins = get_admins(company)

    if admins.exists():
        return admins

    return Membership.objects.filter(
        company=company,
        role=Membership.RoleChoices.OWNER,
    ).select_related("user")


def mark_notification_as_read(
    *,
    recipient,
    invitation,
    notification_type,
    metadata=None,
):
    """
    Mark unread notifications as read.
    """
    return (
        Notification.objects.filter(
            recipient=recipient,
            invitation=invitation,
            notification_type=notification_type,
            status=Notification.NotificationStatus.UNREAD,
        )
        .update(
            status=Notification.NotificationStatus.READ,
            read_at=timezone.now(),
            metadata=metadata or {},
        )
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
    """
    Create a notification for a single user.
    """
    notification = Notification.objects.create(
        **_notification_data(
            recipient=recipient,
            sender=sender,
            notification_type=notification_type,
            title=title,
            message=message,
            action_url=action_url,
            invitation=invitation,
            company=company,
            metadata=metadata,
        )
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
    """
    Send the same notification to all company admins.
    """
    admins = _get_company_admins(company)

    if not admins.exists():
        logger.warning(
            "No admins found for company %s",
            company.id,
        )
        return 0

    notifications = [
        Notification(
            **_notification_data(
                recipient=admin.user,
                sender=sender,
                notification_type=notification_type,
                title=title,
                message=message,
                action_url=action_url,
                invitation=invitation,
                company=company,
                metadata=metadata,
            )
        )
        for admin in admins
    ]

    Notification.objects.bulk_create(notifications)

    invalidate_notification_cache(
        [admin.user.id for admin in admins]
    )

    logger.info(
        "Created %s notifications for company %s",
        len(notifications),
        company.id,
    )

    return len(notifications)