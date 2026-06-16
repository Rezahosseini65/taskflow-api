import logging

from celery import shared_task

from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Company, Membership, Invitation
from taskflow.companies.services.invitation_service import InvitationService
from taskflow.notifications.models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()

def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f'User with id {user_id} does not exist')
        return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_join_request_task(self, company_name, user_id, message=None):
    user = get_user(user_id)
    if user is None:
        return {
            'status': 'error',
            'error': f'Admin user with id {user_id} does not exist'
        }
    try:
        with transaction.atomic():

            company = Company.objects.filter(
                name__iexact=company_name,
                is_active=True
            ).first()

            invitation = Invitation.objects.create(
                email=user.email,
                company=company,
                invited_by=user,
                invited_user=user,
                role=Membership.RoleChoices.MEMBER,
                invitation_type=Invitation.InvitationType.REQUEST,
                token=InvitationService.generate_token(),
                status=Invitation.InvitationStatus.PENDING,
                message=message or f"{user.email} requests to join your company",
                expires_at=InvitationService.create_expiry_date()
            )

            admins_notified = send_notification_to_admins(
                company=company,
                requester_user=user,
                invitation=invitation
            )

            logger.info(
                f"Join request created in Celery: user={user.email}, "
                f"company={company.name}, invitation_id={invitation.id}"
            )

            return {
                'status': 'success',
                'invitation_id': invitation.id,
                'company_id': company.id,
                'company_name': company.name,
                'user_id': user.id,
                'user_email': user.email,
                'invitation_type': invitation.invitation_type,
                'invitation_status': invitation.status,
                'expires_at': invitation.expires_at.isoformat() if invitation.expires_at else None,
                'message': invitation.message,
                'admins_notified': admins_notified,
            }

    except InvitationService.JoinRequestError as e:
        logger.warning(f"Join request validation failed: {str(e)}")
        return {
            'status': 'failed',
            'error': str(e),
            'company_name': company_name,
            'user_email': user.email
        }

    except Exception as e:
        logger.exception(f"Unexpected error in async_create_join_request: {str(e)}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


def send_notification_to_admins(company, requester_user, invitation):

    admin_memberships = Membership.objects.filter(
        company=company,
        role__in=[Membership.RoleChoices.OWNER, Membership.RoleChoices.ADMIN]
    ).select_related('user')

    if not admin_memberships.exists():
            admin_memberships = Membership.objects.filter(
            company=company,
            role=Membership.RoleChoices.OWNER
        ).select_related('user')

    if not admin_memberships.exists():
        logger.warning(f"No owner or admin found for company {company.id}")
        return 0

    notifications = []
    for membership in admin_memberships:
        notification = Notification(
            recipient=membership.user,
            sender=requester_user,
            notification_type=Notification.NotificationType.JOIN_REQUEST,
            title=f"درخواست عضویت جدید در {company.name}",
            message=f"{requester_user.email} درخواست عضویت در {company.name} را دارد.",
            action_url=f"/invitations/review/{invitation.token}/",
            invitation=invitation,
            company=company,
            status=Notification.NotificationStatus.UNREAD
        )
        notifications.append(notification)

    if notifications:
        Notification.objects.bulk_create(notifications)
        logger.info(
            f"Sent {len(notifications)} notifications to admins of {company.name}: "
            f"{[m.user.email for m in admin_memberships]}"
        )

    return len(notifications)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def accept_invitation_task(self, token, admin_id):
    admin_user = get_user(admin_id)

    if admin_user is None:
        return {
            'status': 'error',
            'error': f'Admin user with id {admin_id} does not exist'
        }

    try:
        invitation = Invitation.objects.get(
            token=token,
            status=Invitation.InvitationStatus.PENDING
        )
    except Invitation.DoesNotExist:
        logger.error(f"Invitation with token {token} not found or not pending")
        return {
            'status': 'error',
            'error': 'Invitation not found or already processed'
        }

    is_admin = Membership.objects.filter(
        user=admin_user,
        company=invitation.company,
        role__in=[Membership.RoleChoices.OWNER, Membership.RoleChoices.ADMIN]
    ).exists()

    if not is_admin:
        logger.warning(
            f"User {admin_user.email} is not admin of company {invitation.company.name}"
        )
        raise PermissionError("Only admins can approve join requests")

    try:
        with transaction.atomic():
            membership = invitation.accept(invitation.invited_user)

            notification = Notification.objects.create(
                recipient=invitation.invited_user,
                sender=admin_user,
                notification_type=Notification.NotificationType.JOIN_APPROVED,
                title=f"درخواست عضویت شما در {invitation.company.name} تأیید شد",
                message=f"درخواست شما برای عضویت در {invitation.company.name} توسط {admin_user.email} تأیید شد. خوش آمدید!",
                action_url=f"/companies/{invitation.company.id}/dashboard/",
                invitation=invitation,
                company=invitation.company,
                status=Notification.NotificationStatus.UNREAD,
                metadata={
                    'approved_by': admin_user.id,
                    'approved_by_email': admin_user.email,
                    'approved_at': timezone.now().isoformat(),
                    'membership_id': membership.id,
                    'role': membership.role
                }
            )

            Notification.objects.filter(
                recipient=admin_user,
                invitation=invitation,
                notification_type=Notification.NotificationType.JOIN_REQUEST,
                status=Notification.NotificationStatus.UNREAD
            ).update(
                status=Notification.NotificationStatus.READ,
                read_at=timezone.now(),
                metadata={
                    'auto_marked_as_read': True,
                    'reason': 'request_approved',
                    'approved_by': admin_user.id
                }
            )

            logger.info(
                f"Join request approved: user={invitation.invited_user.email}, "
                f"company={invitation.company.name}, admin={admin_user.email}, "
                f"membership_id={membership.id}, notification_id={notification.id}"
            )

            return {
                'status': 'success',
                'invitation_id': invitation.id,
                'company_id': invitation.company.id,
                'company_name': invitation.company.name,
                'user_id': invitation.invited_user.id,
                'user_email': invitation.invited_user.email,
                'admin_id': admin_user.id,
                'admin_email': admin_user.email,
                'membership_id': membership.id,
                'membership_created': membership.created if hasattr(membership, 'created') else True,
                'notification_id': notification.id,
                'approved_at': timezone.now().isoformat()
            }

    except ValueError as e:
        logger.warning(f"Invitation expired: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'invitation_token': token
        }

    except Exception as e:
        logger.exception(f"Unexpected error in accept_invitation_task: {str(e)}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))

