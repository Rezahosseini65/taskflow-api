from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import Board
from taskflow.accounts.models import CustomUser


class BoardCreateSerializer(serializers.ModelSerializer):
    members = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CustomUser.objects.all(),
        required=False
    )

    class Meta:
        model = Board
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'members'
        ]
        extra_kwargs = {
            'slug': {'required': False},
            'description': {'required': False},
        }

    def validate_slug(self, value):
        if Board.objects.filter(slug=value).exists():
            raise serializers.ValidationError("A board with this slug already exists.")
        return value

class UserSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ('id', 'email')


class BoardListSerializer(serializers.ModelSerializer):
    owner = UserSimpleSerializer()

    class Meta:
        model = Board
        fields = ('id', 'name', 'slug', 'owner', 'created_at')
        read_only_fields = ('id', 'name', 'slug', 'owner', 'created_at')


class BoardDetailSerializer(serializers.ModelSerializer):
    owner = UserSimpleSerializer()
    members = UserSimpleSerializer(many=True)

    class Meta:
        model = Board
        fields = (
            'id',
            'name',
            'slug',
            'description',
            'owner',
            'members',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id',
            'name',
            'slug',
            'description',
            'owner',
            'members',
            'created_at',
            'updated_at'
        )


class BoardUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=False,
        trim_whitespace=True,
        help_text="Board name (optional)"
    )
    description = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Board description (optional)"
    )
    members_to_add = serializers.ListSerializer(
        child=serializers.EmailField(),
        write_only=True,
        required=False,
        default=[],
        help_text="List of emails to add as members"
    )
    members_to_remove = serializers.ListSerializer(
        child=serializers.EmailField(),
        write_only=True,
        required=False,
        default=[],
        help_text="List of emails to remove from members"
    )

    def validate_name(self, value)-> str:
        """Validate board name uniqueness for the same owner."""
        board = self.context['board']
        if value != board.name and Board.objects.filter(
                name=value,
                owner_id=board.owner_id
        ).exists():
            raise ValidationError("You already have a board with this name")
        return value

    def validate_description(self, value)-> str:
        """Validate description length."""
        if value and len(value) > 500:
            raise serializers.ValidationError(
                "Description cannot exceed 500 characters."
            )
        return value

    def validate_members_to_add(self, value)-> list:
        """Validate that all emails to add exist in the system."""
        if not value:
            return []

        unique_emails = list(set(value))

        existing_users = CustomUser.objects.filter(
            email__in=unique_emails
        ).values_list('email', flat=True)

        invalid_emails = set(unique_emails) - set(existing_users)
        if invalid_emails:
            raise serializers.ValidationError(
                f"User(s) not found: {', '.join(invalid_emails)}"
            )

        return unique_emails

    def validate_members_to_remove(self, value)-> list:
        """Remove duplicates from members to remove list."""
        if not value:
            return []

        return list(set(value))

    def validate(self, data)-> dict:
        """
        Cross-field validation for member operations:
        - Cannot remove board owner
        - Cannot add board owner (already member)
        - Cannot add and remove same user
        - Cannot add already existing members
        - Cannot remove non-members
        """
        board = self.context.get('board')
        if not board:
            raise serializers.ValidationError(
                "Board instance is required in context."
            )

        members_to_add = data.get('members_to_add', [])
        members_to_remove = data.get('members_to_remove', [])

        # Owner cannot be removed
        if members_to_remove and board.owner.email in members_to_remove:
            raise serializers.ValidationError({
                "members_to_remove": "Cannot remove board owner from members."
            })

        # Owner is already a member by default
        if members_to_add and board.owner.email in members_to_add:
            raise serializers.ValidationError({
                "members_to_add": "Board owner is already a member by default."
            })

        # Cannot add and remove same user
        common_emails = set(members_to_add) & set(members_to_remove)
        if common_emails:
            raise serializers.ValidationError(
                f"Cannot add and remove the same user(s): {', '.join(common_emails)}"
            )

        # Check for already existing members
        if members_to_add:
            existing_members = board.members.filter(
                email__in=members_to_add
            ).values_list('email', flat=True)

            already_members = set(members_to_add) & set(existing_members)
            if already_members:
                raise serializers.ValidationError({
                    "members_to_add": f"User(s) already members: {', '.join(already_members)}"
                })

        # Check for non-members in removal list
        if members_to_remove:
            existing_members = board.members.filter(
                email__in=members_to_remove
            ).values_list('email', flat=True)

            non_members = set(members_to_remove) - set(existing_members)
            if non_members:
                raise serializers.ValidationError({
                    "members_to_remove": f"User(s) not members: {', '.join(non_members)}"
                })

        return data
