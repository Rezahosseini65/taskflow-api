from rest_framework import serializers

from .models import Company
from taskflow.accounts.models import CustomUser


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