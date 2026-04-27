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