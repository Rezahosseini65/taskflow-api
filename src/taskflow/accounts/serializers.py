from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from .validators import validate_strong_password, phone_number_validator
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


class UserReadSerializer(serializers.ModelSerializer):

    class Meta:
        model = CustomUser
        fields = (
            'email', 'first_name', 'last_name', 'display_name',
            'avatar', 'phone_number', 'email_notifications_enabled', 'date_joined'
        )


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = (
            'first_name', 'last_name', 'display_name',
            'avatar', 'phone_number', 'email_notifications_enabled'
        )
        extra_kwargs = {
            'first_name': {'required': False, 'allow_blank': False},
            'last_name': {'required': False, 'allow_blank': False},
            'display_name': {'required': False, 'allow_blank': False},
            'phone_number': {
                'required': False,
                'allow_blank': False,
                'validators': [phone_number_validator]
            },
            'email_notifications_enabled': {'required': False},
            'avatar': {'required': False},
        }

    def update(self, instance, validated_data):

        updated_fields = []

        for field, value in validated_data.items():
            if getattr(instance, field) != value:
                setattr(instance, field, value)
                updated_fields.append(field)

        if updated_fields:
            instance.save(update_fields=updated_fields)
        else:
            pass

        return instance



