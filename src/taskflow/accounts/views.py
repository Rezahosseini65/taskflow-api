import logging

from django.conf import settings
from django.db import transaction

from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response

from .serializers import UserRegisterSerializer
from .models import CustomUser
from taskflow.utils.services import TokenCookieManager, generate_access_refresh_tokens

logger = logging.getLogger(__name__)

# Create your views here.


class UserRegisterView(APIView):
    """
    View for handling user registration.

    This view processes POST requests to register new users. It validates the incoming data
    using `UserRegisterSerializer`, creates a new user in the database, generates JWT access
    and refresh tokens, and sets these tokens as HTTP-only cookies in the response.
    The entire process is wrapped in a database transaction to ensure atomicity.
    """
    def post(self, request):

        serializer = UserRegisterSerializer(data=request.data)

        if serializer.is_valid():

            validated_data = serializer.validated_data
            password = validated_data.pop("password")
            validated_data.pop("confirm_password", None)

            with transaction.atomic():
                try:
                    user = CustomUser.objects.create_user(**validated_data, password=password)

                    access_token, refresh_token = generate_access_refresh_tokens(user=user)

                    response = Response(
                        {"detail": "Registration successful"},
                        status=status.HTTP_201_CREATED
                    )

                    TokenCookieManager.set_access_cookie(response, access_token)
                    TokenCookieManager.set_refresh_cookie(response, refresh_token)

                    return response

                except Exception as e:
                    logger.error(f"User registration failed: {str(e)}", exc_info=True)
                    if settings.DEBUG:
                        return Response(
                            {"detail": f"An error occurred: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )

        logger.warning(f"Register validation failed: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

