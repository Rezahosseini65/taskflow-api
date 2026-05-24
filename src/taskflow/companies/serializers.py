from rest_framework import serializers

from .models import Company, Membership
from taskflow.accounts.models import CustomUser


class CompanyCreateSerializer(serializers.ModelSerializer):
    members = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CustomUser.objects.all(),
        required=False,
        write_only=True
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


class MemberWithRoleSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    role = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = Membership
        fields = ('user_id', 'email', 'role', 'joined_at')


class CompanyDetailSerializer(serializers.ModelSerializer):

    owner = UserSimpleSerializer(read_only=True)
    members = serializers.SerializerMethodField(read_only=True)

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

    def get_members(self, obj):

        if hasattr(obj, '_prefetched_memberships'):
            memberships = obj._prefetched_memberships
            return MemberWithRoleSerializer(memberships, many=True).data

        memberships = Membership.objects.filter(
            company_id=obj.id
        ).select_related('user').only(
            'role', 'joined_at',
            'user__id', 'user__email'
        )
        obj._prefetched_memberships = memberships

        return MemberWithRoleSerializer(memberships, many=True).data