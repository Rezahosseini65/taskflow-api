import logging
import secrets
from datetime import timedelta

from celery import shared_task

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Company, Invitation, Membership
from .services import is_company_admin
from taskflow.notifications.models import Notification
from taskflow.notifications.notification_service import (
    create_notification,
    notify_company_admins,
    invalidate_notification_cache,
    mark_notification_as_read,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def get_user(user_id):
    """
    Return user instance or None.
    """
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error("User %s does not exist.", user_id)
        return None


def get_pending_invitation(token):
    """
    Return pending invitation.
    """
    try:
        return Invitation.objects.get(
            token=token,
            status=Invitation.InvitationStatus.PENDING,
        )
    except Invitation.DoesNotExist:
        logger.error(
            "Pending invitation with token %s not found.",
            token,
        )
        raise

# ---------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_join_request_task(
    self,
    company_name,
    user_id,
    message=None,
):
    """
    Create a join request and notify company admins.
    """

    user = get_user(user_id)

    if user is None:
        return {
            "status": "error",
            "error": f"User with id {user_id} does not exist",
        }

    try:
        with transaction.atomic():

            company = Company.objects.filter(
                name__iexact=company_name,
                is_active=True,
            ).first()

            if company is None:
                return {
                    "status": "error",
                    "error": f"Company '{company_name}' not found",
                }

            existing = Invitation.objects.filter(
                email=user.email,
                company=company,
                status=Invitation.InvitationStatus.PENDING,
            ).exists()

            if existing:
                return {
                    "status": "error",
                    "error": "Pending invitation already exists.",
                }

            invitation = Invitation.objects.create(
                email=user.email,
                company=company,
                invited_by=user,
                invited_user=user,
                role=Membership.RoleChoices.MEMBER,
                invitation_type=Invitation.InvitationType.REQUEST,
                token=secrets.token_urlsafe(32),
                status=Invitation.InvitationStatus.PENDING,
                message=(
                    message
                    or f"{user.email} requests to join your company"
                ),
                expires_at=timezone.now() + timedelta(days=7),
            )

            admins_notified = notify_company_admins(
                company=company,
                sender=user,
                invitation=invitation,
                notification_type=Notification.NotificationType.JOIN_REQUEST,
                title=f"درخواست عضویت جدید در {company.name}",
                message=(
                    f"{user.email} درخواست عضویت در "
                    f"{company.name} را دارد."
                ),
                action_url=f"/invitations/review/{invitation.token}/",
            )

            logger.info(
                "Join request created: "
                "user=%s company=%s invitation=%s",
                user.email,
                company.name,
                invitation.id,
            )

            return {
                "status": "success",
                "invitation_id": invitation.id,
                "company_id": company.id,
                "company_name": company.name,
                "user_id": user.id,
                "user_email": user.email,
                "invitation_type": invitation.invitation_type,
                "invitation_status": invitation.status,
                "expires_at": (
                    invitation.expires_at.isoformat()
                    if invitation.expires_at
                    else None
                ),
                "message": invitation.message,
                "admins_notified": admins_notified,
            }

    except Exception as exc:

        logger.exception(
            "Unexpected error while creating join request."
        )

        raise self.retry(
            exc=exc,
            countdown=60 * (self.request.retries + 1),
        )

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def accept_invitation_task(self, token, admin_id):
    """
    Approve a pending join request.
    """

    admin_user = get_user(admin_id)

    if admin_user is None:
        return {
            "status": "error",
            "error": f"Admin user with id {admin_id} does not exist",
        }

    try:
        invitation = get_pending_invitation(token)
    except Invitation.DoesNotExist:
        return {
            "status": "error",
            "error": "Invitation not found or already processed",
        }

    if not is_company_admin(admin_user, invitation.company):
        logger.warning(
            "User %s is not admin of company %s",
            admin_user.email,
            invitation.company.name,
        )
        raise PermissionError("Only admins can approve join requests")

    try:
        with transaction.atomic():

            membership, created = invitation.accept(invitation.invited_user)

            notification = create_notification(
                recipient=invitation.invited_user,
                sender=admin_user,
                notification_type=Notification.NotificationType.JOIN_APPROVED,
                title=f"درخواست عضویت شما در {invitation.company.name} تأیید شد",
                message=(
                    f"درخواست شما برای عضویت در "
                    f"{invitation.company.name} توسط "
                    f"{admin_user.email} تأیید شد. خوش آمدید!"
                ),
                action_url=f"/companies/{invitation.company.id}/dashboard/",
                invitation=invitation,
                company=invitation.company,
                metadata={
                    "approved_by": admin_user.id,
                    "approved_by_email": admin_user.email,
                    "approved_at": timezone.now().isoformat(),
                    "membership_id": membership.id,
                    "role": membership.role,
                },
            )

            mark_notification_as_read(
                recipient=admin_user,
                invitation=invitation,
                notification_type=Notification.NotificationType.JOIN_REQUEST,
                metadata={
                    "auto_marked_as_read": True,
                    "reason": "request_approved",
                    "approved_by": admin_user.id,
                },
            )

            invalidate_notification_cache(
                [
                    invitation.invited_user.id,
                    admin_user.id,
                ]
            )

            logger.info(
                "Join request approved: "
                "user=%s company=%s admin=%s membership_id=%s",
                invitation.invited_user.email,
                invitation.company.name,
                admin_user.email,
                membership.id,
            )

            return {
                "status": "success",
                "invitation_id": invitation.id,
                "company_id": invitation.company.id,
                "company_name": invitation.company.name,
                "user_id": invitation.invited_user.id,
                "user_email": invitation.invited_user.email,
                "admin_id": admin_user.id,
                "admin_email": admin_user.email,
                "membership_id": membership.id,
                "membership_created": created,
                "notification_id": notification.id,
                "approved_at": timezone.now().isoformat(),
            }

    except ValueError as exc:

        logger.warning(
            "Invitation expired: %s",
            exc,
        )

        return {
            "status": "error",
            "error": str(exc),
            "invitation_token": token,
        }

    except Exception as exc:

        logger.exception(
            "Unexpected error while approving invitation."
        )

        raise self.retry(
            exc=exc,
            countdown=60 * (self.request.retries + 1),
        )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def reject_invitation_task(self, token, admin_id, reason=None):
    """
    Reject a pending join request.
    """

    admin_user = get_user(admin_id)

    if admin_user is None:
        return {
            "status": "error",
            "error": f"Admin user with id {admin_id} does not exist",
        }

    try:
        invitation = get_pending_invitation(token)
    except Invitation.DoesNotExist:
        return {
            "status": "error",
            "error": "Invitation not found or already processed",
        }

    if not is_company_admin(admin_user, invitation.company):
        logger.warning(
            "User %s is not admin of company %s",
            admin_user.email,
            invitation.company.name,
        )
        raise PermissionError("Only admins can reject join requests")

    try:
        with transaction.atomic():

            invitation.status = Invitation.InvitationStatus.CANCELLED
            invitation.save(update_fields=["status"])

            reject_message = (
                f"درخواست شما برای عضویت در "
                f"{invitation.company.name} توسط "
                f"{admin_user.email} رد شد."
            )

            if reason:
                reject_message += f" دلیل: {reason}"

            notification = create_notification(
                recipient=invitation.invited_user,
                sender=admin_user,
                notification_type=Notification.NotificationType.JOIN_REJECTED,
                title=f"درخواست عضویت شما در {invitation.company.name} رد شد",
                message=reject_message,
                action_url=f"/companies/{invitation.company.id}/dashboard/",
                invitation=invitation,
                company=invitation.company,
                metadata={
                    "rejected_by": admin_user.id,
                    "rejected_by_email": admin_user.email,
                    "rejected_at": timezone.now().isoformat(),
                    "reason": reason,
                },
            )

            mark_notification_as_read(
                recipient=admin_user,
                invitation=invitation,
                notification_type=Notification.NotificationType.JOIN_REQUEST,
                metadata={
                    "auto_marked_as_read": True,
                    "reason": "request_rejected",
                    "rejected_by": admin_user.id,
                    "rejected_at": timezone.now().isoformat(),
                },
            )

            invalidate_notification_cache(
                [
                    invitation.invited_user.id,
                    admin_user.id,
                ]
            )

            logger.info(
                "Join request rejected: "
                "user=%s company=%s admin=%s reason=%s",
                invitation.invited_user.email,
                invitation.company.name,
                admin_user.email,
                reason or "No reason provided",
            )

            return {
                "status": "success",
                "invitation_id": invitation.id,
                "company_id": invitation.company.id,
                "company_name": invitation.company.name,
                "user_id": invitation.invited_user.id,
                "user_email": invitation.invited_user.email,
                "admin_id": admin_user.id,
                "admin_email": admin_user.email,
                "notification_id": notification.id,
                "rejected_at": timezone.now().isoformat(),
                "reason": reason,
            }

    except ValueError as exc:

        logger.warning(
            "Invitation error: %s",
            exc,
        )

        return {
            "status": "error",
            "error": str(exc),
            "invitation_token": token,
        }

    except Exception as exc:

        logger.exception(
            "Unexpected error while rejecting invitation."
        )

        raise self.retry(
            exc=exc,
            countdown=60 * (self.request.retries + 1),
        )

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_member_invitation_task(
    self,
    company_id,
    invited_user_id,
    inviter_id,
    role=Membership.RoleChoices.MEMBER,
):
    try:
        company = Company.objects.get(
            id=company_id,
            is_active=True,
        )
    except Company.DoesNotExist:
        logger.error(
            "Company with id %s not found.",
            company_id,
        )
        return {
            "status": "error",
            "error": "Company not found or not active",
        }

    invited_user = get_user(invited_user_id)
    inviter = get_user(inviter_id)

    if invited_user is None or inviter is None:
        logger.error(
            "Invited user %s or inviter %s not found.",
            invited_user_id,
            inviter_id,
        )
        return {
            "status": "error",
            "error": "User not found",
        }

    try:
        with transaction.atomic():

            invitation = Invitation.objects.create(
                email=invited_user.email,
                company=company,
                invited_by=inviter,
                invited_user=invited_user,
                role=role,
                invitation_type=Invitation.InvitationType.MEMBER_INVITE,
                token=secrets.token_urlsafe(32),
                status=Invitation.InvitationStatus.PENDING,
                message=f"{inviter.email} invites you to join {company.name}",
                expires_at=timezone.now() + timedelta(days=7),
            )

            notification = create_notification(
                recipient=invited_user,
                sender=inviter,
                notification_type=Notification.NotificationType.INVITATION,
                title=f"دعوت به عضویت در {company.name}",
                message=(
                    f"{inviter.email} شما را به عضویت در "
                    f"{company.name} دعوت کرده است."
                ),
                action_url=f"/invitations/accept/{invitation.token}/",
                invitation=invitation,
                company=company,
                metadata={
                    "invitation_type": "member_invite",
                    "invited_by": inviter.id,
                    "invited_by_email": inviter.email,
                    "role": role,
                },
            )

            invalidate_notification_cache(invited_user.id)

            logger.info(
                "Member invitation created: inviter=%s invited=%s company=%s",
                inviter.email,
                invited_user.email,
                company.name,
            )

            return {
                "status": "success",
                "invitation_id": invitation.id,
                "company_id": company.id,
                "company_name": company.name,
                "invited_user_id": invited_user.id,
                "invited_user_email": invited_user.email,
                "inviter_id": inviter.id,
                "inviter_email": inviter.email,
                "role": role,
                "expires_at": invitation.expires_at.isoformat(),
                "notification_id": notification.id,
            }

    except Exception as exc:
        logger.exception(
            "Unexpected error while creating member invitation."
        )
        raise self.retry(
            exc=exc,
            countdown=60 * (self.request.retries + 1),
        )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def member_accept_invitation_task(self, token, user_id):
    """
    Accept a member invitation.
    """

    user = get_user(user_id)

    if user is None:
        return {
            "status": "error",
            "error": f"User with id {user_id} does not exist",
        }

    try:
        invitation = get_pending_invitation(token)
    except Invitation.DoesNotExist:
        return {
            "status": "error",
            "error": "Invitation not found or already processed",
        }

    try:
        with transaction.atomic():

            membership, created = invitation.accept(user)

            logger.info(
                "Member invitation accepted: "
                "user=%s company=%s membership=%s",
                user.email,
                invitation.company.name,
                membership.id,
            )

            return {
                "status": "success",
                "membership_id": membership.id,
                "invitation_id": invitation.id,
                "company_id": invitation.company.id,
                "company_name": invitation.company.name,
                "user_id": user.id,
                "user_email": user.email,
                "accepted_at": timezone.now().isoformat(),
            }

    except ValueError as exc:

        logger.warning(
            "Invitation error: %s",
            exc,
        )

        return {
            "status": "error",
            "error": str(exc),
            "invitation_token": token,
        }

    except Exception as exc:

        logger.exception(
            "Unexpected error while accepting member invitation."
        )

        raise self.retry(
            exc=exc,
            countdown=60 * (self.request.retries + 1),
        )