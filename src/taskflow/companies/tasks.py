import logging

from celery import shared_task

from django.db.models import Exists, OuterRef
from django.db import transaction

from .models import Company, Membership, Invitation
from taskflow.companies.services.invitation_service import InvitationService
from taskflow.notifications.models import Notification

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_join_request_task(self, company_name, user_id, message=None):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        user = User.objects.get(id=user_id)

    except User.DoesNotExist:
        return {
            'status': 'error',
            'error': f'User with id {user_id} does not exist'
        }

    try:
        with transaction.atomic():
            company = Company.objects.filter(
                name__iexact=company_name,
                is_active=True
            ).annotate(
                is_member=Exists(
                    Membership.objects.filter(user=user, company_id=OuterRef("id"))
                ),
                has_pending_request=Exists(
                    Invitation.objects.filter(
                        email=user.email,
                        company_id=OuterRef('id'),
                        status=Invitation.InvitationStatus.PENDING,
                        invitation_type=Invitation.InvitationType.REQUEST
                    )
                )
            ).only('id', 'email').first()

            if not company:
                raise InvitationService.JoinRequestError("Company does not exist or is not active.")

            if company.is_member:
                raise InvitationService.JoinRequestError("You are already a member of this company")

            if company.has_pending_request:
                raise InvitationService.JoinRequestError("You already have a pending join request")

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