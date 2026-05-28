import secrets
from datetime import timedelta

from django.utils import timezone
from rest_framework.generics import get_object_or_404

from taskflow.companies.models import Company, Membership, Invitation


class InvitationService:

    @staticmethod
    def generate_token()->str:
        """Generate unique token for invitation"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def create_expiry_date(days=7):
        """Create expiry date for invitation"""
        return timezone.now() + timedelta(days=days)

    @staticmethod
    def create_join_request(company_id, user, message=None):
        company = get_object_or_404(
            Company,
            id=company_id
        )

        if Membership.objects.filter(
            user=user,
            company=company
        ).exists():
            raise ValueError("You are already a member of this company")

        existing_request = Invitation.objects.filter(
            email=user.email,
            company=company,
            status=Invitation.InvitationStatus.PENDING,
            invitation_type=Invitation.InvitationType.REQUEST
        ).exists()

        if existing_request:
            raise ValueError("You already have a pending join request")

        invitation = Invitation.objects.create(
            email=user.email,
            company=company,
            invited_by=user,
            invited_user=user,
            role = Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token=InvitationService.generate_token(),
            status=Invitation.InvitationStatus.PENDING,
            message=message or f"{user.get_full_name()} requests to join your company",
            expires_at=InvitationService.create_expiry_date(days=30)
        )

        return invitation

    @staticmethod
    def approve_join_request(invitation_id, admin_user):
        invitation = get_object_or_404(
            Invitation,
            id=invitation_id
        )

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
            Invitation,
            id=invitation_id
        )

        membership = Membership.objects.filter(
            user=admin_user,
            company=invitation.company,
            role=Membership.RoleChoices.ADMIN
        ).exists()

        if not membership:
            raise PermissionError("Only admins can reject join requests")

        invitation.status = Invitation.InvitationStatus.REJECTED
        invitation.save()

        return invitation


