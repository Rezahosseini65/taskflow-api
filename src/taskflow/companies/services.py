from .models import Membership


def get_admins(company):
    """
    Return all company admins (including owners).
    """
    return (
        Membership.objects.filter(
            company=company,
            role__in=[
                Membership.RoleChoices.OWNER,
                Membership.RoleChoices.ADMIN,
            ],
        )
        .select_related("user")
    )


def is_company_admin(user, company):
    """
    Check whether the user is an owner or admin of the company.
    """
    return Membership.objects.filter(
        user=user,
        company=company,
        role__in=[
            Membership.RoleChoices.OWNER,
            Membership.RoleChoices.ADMIN,
        ],
    ).exists()