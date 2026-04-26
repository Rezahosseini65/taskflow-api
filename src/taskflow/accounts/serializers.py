from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from .validators import validate_strong_password
from .models import CustomUser


class UserRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        validators=[validate_strong_password],
        style={'input_type':'password'}
    )
    confirm_password = serializers.CharField(
        required=True,
        style={'input_type':'password'}
    )

    def validate_email(self, value) -> str:
        """
        Checks if the email already exists in the database.
        """
        if CustomUser.objects.filter(email=value).exists():
            raise ValidationError(
                _("This email address is already in use. Please use another one."),
                code='email_already_exists'
            )

        return value

    def validate(self, data: dict)-> dict:
        """
        Custom validation to ensure that the password and confirm_password match.
        """
        password = data.get("password")
        confirm_password = data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise ValidationError(
                _("Passwords do not match."),
                code='passwords_mismatch'
            )

        return data


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        style={'input_type':'password'},
        write_only=True
    )

    def validate(self, attrs)-> dict:
        email = attrs.get("email")
        password = attrs.get("password")

        user = authenticate(email=email, password=password)

        if not user:
            raise ValidationError(
                _("Your email or password is incorrect, please try again")
            )

        attrs["user"] = user
        return attrs