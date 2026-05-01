from rest_framework import serializers

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
        if Board.objects.filter(slug=value):
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
            'created_at'
        )
        read_only_fields = (
            'id',
            'name',
            'slug',
            'description',
            'owner',
            'members',
            'created_at'
        )