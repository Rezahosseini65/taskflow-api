from django.db.models import Exists, OuterRef
from django.utils.text import slugify

from rest_framework import serializers

from .models import Company, Membership, Invitation
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

    def validate(self, data):
        """
        Check that the company name and slug are unique.
        """
        name = data.get('name')
        slug = data.get('slug')

        if not slug:
            slug = slugify(name, allow_unicode=True)

        if Company.objects.filter(name__iexact=name).exists():
            raise serializers.ValidationError({
                "name": "A company with this name already exists."
            })

        if Company.objects.filter(slug=slug).exists():
            raise serializers.ValidationError({
                "slug": "A company with this slug already exists."
            })

        data['slug'] = slug

        return data


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

        memberships = Membership.objects.filter(
            company_id=obj.id
        ).select_related('user').only(
            'role', 'joined_at',
            'user__id', 'user__email'
        )

        return MemberWithRoleSerializer(memberships, many=True).data


class RequestJoinCompanySerializer(serializers.Serializer):
    company_name = serializers.CharField(
        max_length=128,
        write_only=True,
        trim_whitespace=True
    )
    message = serializers.CharField(
        max_length=1024,
        required=False,
        write_only=True,
        allow_blank=True
    )

    def validate_company_name(self, value):
        self.context['company_name'] = value.strip()
        return value


class SendMemberInvitationSerializer(serializers.Serializer):
    user_email = serializers.EmailField(
        required=True,
    )
    role = serializers.ChoiceField(
        choices=Membership.RoleChoices.choices,
        default=Membership.RoleChoices.MEMBER
    )

    def validate(self, data):
        company = self.context.get('company')

        user_email = data.get('user_email')

        invited_user = CustomUser.objects.filter(
            email=user_email,
            is_active=True
        ).annotate(
            is_member=Exists(
                Membership.objects.filter(
                    user_id=OuterRef('id'),
                    company=company,
                )
            ),
            has_pending_invitation=Exists(
                Invitation.objects.filter(
                    invited_user_id=OuterRef('id'),
                    company=company,
                    status=Invitation.InvitationStatus.PENDING
                )
            )
        ).only('id', 'email', 'is_active').first()

        if not invited_user:
            raise serializers.ValidationError(
                f"No user found with email: {user_email}"
            )

        self.context['invited_user'] = invited_user

        if invited_user.is_member:
            raise serializers.ValidationError(
                f"{invited_user.email} is already a member"
            )

        if invited_user.has_pending_invitation:
            raise serializers.ValidationError(
                f"An invitation already exists for {invited_user.email}"
            )

        inviter = self.context.get('inviter')
        if inviter and invited_user.id == inviter.id:
            raise serializers.ValidationError(
                "You cannot invite yourself to the company"
            )

        return data