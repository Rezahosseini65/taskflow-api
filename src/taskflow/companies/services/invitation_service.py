import secrets
from datetime import timedelta

from django.utils import timezone

from rest_framework.generics import get_object_or_404

from taskflow.companies.models import Membership, Invitation


class InvitationService:

    class JoinRequestError(Exception):
        pass

    @staticmethod
    def generate_token()->str:
        """Generate unique token for invitation"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_expiry_date(days=7):
        """Create expiry date for invitation"""
        return timezone.now() + timedelta(days=days)

    @staticmethod
    def approve_join_request(invitation_id, admin_user):
        invitation = get_object_or_404(
            Invitation.objects.select_related('company', 'invited_user'),
            id=invitation_id
        )

        # Check if already approved
        if invitation.status == Invitation.InvitationStatus.ACCEPTED:
            raise ValueError("This request has already been approved")

        # Check if already rejected
        if invitation.status == Invitation.InvitationStatus.CANCELLED:
            raise ValueError("This request has already been rejected")

        membership = Membership.objects.filter(
            user=admin_user,
            company=invitation.company,
            role=Membership.RoleChoices.ADMIN
        ).exists()

        if not membership:
            raise PermissionError("Only admins can approve join requests")

        membership = invitation.accept(invitation.invited_user)

        return membership

    @staticmethod
    def reject_join_request(invitation_id, admin_user, reason=None):
        invitation = get_object_or_404(
            Invitation.objects.select_related('company', 'invited_user'),
            id=invitation_id
        )

        membership = Membership.objects.filter(
            user=admin_user,
            company=invitation.company,
            role=Membership.RoleChoices.ADMIN
        ).exists()

        if not membership:
            raise PermissionError("Only admins can reject join requests")

        invitation.status = Invitation.InvitationStatus.CANCELLED
        invitation.save()

        return invitation


