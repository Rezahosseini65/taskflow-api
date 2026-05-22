from rest_framework import serializers

from .models import Company
from taskflow.accounts.models import CustomUser


class CompanyCreateSerializer(serializers.ModelSerializer):
    members = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CustomUser.objects.all(),
        required=False
    )

    class Meta:
        model = Company
        fields = (
            'id', 'name', 'slug', 'email', 'website',
            'description', 'logo', 'members',
        )
        extra_kwargs = {
            'slug': {'required': False},
            'description': {'required': False},
            'email':{'required': False},
            'website':{'required': False},
            'logo': {'required': False},
        }

    def validate_slug(self, value):
        if Company.objects.filter(slug=value).exists():
            raise serializers.ValidationError("A company with this slug already exists.")

        return value


class UserSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'email')


class CompanyDetailSerializer(serializers.ModelSerializer):

    owner = UserSimpleSerializer(read_only=True)
    members = UserSimpleSerializer(many=True, read_only=True)

    class Meta:
        model = Company
        fields = (
            'id', 'name', 'slug', 'email', 'website',
            'description', 'logo', 'owner', 'members',
            'is_active', 'created_at', 'updated_at'
        )
        read_only_fields = (
            'id', 'name', 'slug', 'email',
            'website', 'description', 'logo',
            'is_active', 'created_at', 'updated_at'
        )