import re

from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


def validate_strong_password(password: str) -> None:
    """
    Password strength validation:
        - Minimum 8 characters
        - Contains lowercase letters
        - Contains uppercase letters
        - Contains digits
    """
    if len(password) < 8:
        raise ValidationError(
            _("Password must be at least 8 characters long."),
            code='too_short'
        )

    if not re.search(r'[A-Z]', password):
        raise ValidationError(
            _("Password must contain at least one uppercase letter."),
            code='no_uppercase'
        )

    if not re.search(r'[a-z]', password):
        raise ValidationError(
            _("Password must contain at least one lowercase letter."),
            code='no_lowercase'
        )

    if not re.search(r'\d', password):
        raise ValidationError(
            _("Password must contain at least one digit."),
            code='no_digit'
        )