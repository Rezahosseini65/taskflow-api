import datetime
import logging # Assuming logger is used elsewhere or might be needed

from django.conf import settings
from django.utils import timezone

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response


# Configure logging if not already done
logger = logging.getLogger(__name__)


def generate_access_refresh_tokens(user):
    """
    Generates JWT access and refresh tokens for a given user.

    Args:
        user: The user object for whom tokens are to be generated.

    Returns:
        A tuple containing the access token string and the refresh token string.
    """
    # Create a refresh token instance for the user
    refresh = RefreshToken.for_user(user)
    # Access the access token from the refresh token
    access = refresh.access_token

    # Return both tokens as strings
    return str(access), str(refresh)

class TokenCookieManager:
    """
    Manages the setting and deletion of JWT access and refresh tokens in HTTP cookies.
    Uses settings from SIMPLE_JWT in Django's settings.py.
    """

    @staticmethod
    def set_access_cookie(response: Response, access_token: str):
        """
        Sets the access token in an HTTP-only cookie on the response.
        """
        access_token_lifetime_days = settings.SIMPLE_JWT.get("REFRESH_TOKEN_LIFETIME", datetime.timedelta(days=7)).days
        expires_delta = datetime.timedelta(days=access_token_lifetime_days)

        response.set_cookie(
            key=settings.SIMPLE_JWT["AUTH_COOKIE"],
            value=access_token,
            httponly=settings.SIMPLE_JWT["AUTH_COOKIE_HTTP_ONLY"],
            secure=settings.SIMPLE_JWT["AUTH_COOKIE_SECURE"],
            samesite=settings.SIMPLE_JWT["AUTH_COOKIE_SAMESITE"],
            path=settings.SIMPLE_JWT["AUTH_COOKIE_PATH"],
            expires=timezone.now() + expires_delta
        )

    @staticmethod
    def set_refresh_cookie(response: Response, refresh_token: str):
        """
        Sets the refresh token in an HTTP-only cookie on the response.
        """
        # Use the configured lifetime for the refresh token from Django settings
        refresh_token_lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]

        response.set_cookie(
            key=settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"],
            value=refresh_token,
            httponly=settings.SIMPLE_JWT["AUTH_COOKIE_HTTP_ONLY"],
            secure=settings.SIMPLE_JWT["AUTH_COOKIE_SECURE"],
            samesite=settings.SIMPLE_JWT["AUTH_COOKIE_SAMESITE"],
            path=settings.SIMPLE_JWT["AUTH_COOKIE_PATH"],
            expires=timezone.now() + refresh_token_lifetime
        )

    @staticmethod
    def delete_tokens_cookies(response: Response):
        """
        Deletes both the access and refresh token cookies from the client's browser.
        """
        response.delete_cookie(settings.SIMPLE_JWT["AUTH_COOKIE"])
        response.delete_cookie(settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"])

        return response
