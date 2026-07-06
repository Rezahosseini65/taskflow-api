import logging

from django.conf import settings
from django.db import transaction, IntegrityError

from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser
from .throttles import UserRegisterThrottle, UserLoginThrottle
from .authentication import CookieJWTAuthentication
from taskflow.utils.services import TokenCookieManager, generate_access_refresh_tokens
from .serializers import (
    UserRegisterSerializer,
    UserLoginSerializer,
    UserUpdateSerializer,
    UserReadSerializer
)

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
    #TODO: UserRegisterThrottle will be enabled later
    #throttle_classes = [UserRegisterThrottle]
    authentication_classes = []

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

                except IntegrityError:
                    return Response(
                        {
                            "email": [
                                "This email address is already in use. Please use another one."
                            ]
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )


                except Exception as e:
                    logger.error(f"User registration failed: {str(e)}", exc_info=True)
                    if settings.DEBUG:
                        return Response(
                            {"detail": f"An error occurred: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )

        logger.warning(f"Register validation failed: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserLoginView(APIView):
    #TODO: UserLoginThrottle will be enabled later
    #throttle_classes = [UserLoginThrottle]
    authentication_classes = []
    def post(self, request):

        serializer = UserLoginSerializer(data=request.data)

        if serializer.is_valid():
            try:
                user = serializer.validated_data.get("user")
                access_token, refresh_token = generate_access_refresh_tokens(user=user)

                response = Response(
                    {'detail':'Login successful'},
                    status=status.HTTP_200_OK
                )

                TokenCookieManager.set_access_cookie(response, access_token)
                TokenCookieManager.set_refresh_cookie(response, refresh_token)

                return response

            except Exception as e:
                logger.error(f"User login failed: {str(e)}", exc_info=True)
                if settings.DEBUG:
                    return Response(
                        {"detail": f"An error occurred: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                return Response(
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        logger.warning(f"Login validation failed: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RefreshAccessTokenView(APIView):
    """
    Handles POST requests to refresh the access token.

    Reads the 'refresh_token' from the request cookies. If found and valid,
    it generates a new access token and returns a success response with the
    new token set as an HTTP-only cookie. If the refresh token is missing
    or invalid, it returns an appropriate error response.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token')
        if refresh_token is None:
            return Response(
                {'detail': 'No refresh token found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            response = Response(
                {'detail': 'access token set'}
            )

            TokenCookieManager.set_access_cookie(response, access_token)

            return response

        except Exception as e:
            logger.error(f"detail: Token is invalid or expired. {str(e)}", exc_info=True)
            if settings.DEBUG:
                return Response(
                    {"detail": f"An error occurred: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class UserLogoutView(APIView):

    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        response = Response (
            {"detail": "Logout successful"},
            status=status.HTTP_200_OK
        )

        TokenCookieManager.delete_tokens_cookies(response)

        return response


class UserUpdateView(APIView):

    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = UserReadSerializer(user)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    def patch(self, request):
        user = request.user
        serializer = UserUpdateSerializer(
            user,
            data=request.data,
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_200_OK
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )



