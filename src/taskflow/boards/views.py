import logging

from django.db import transaction
from django.utils.text import slugify
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .serializers import BoardCreateSerializer
from .models import Board

logger = logging.getLogger(__name__)

# Create your views here.


class BoardCreateView(APIView):

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = BoardCreateSerializer(data=request.data, context={'request':request})
        if serializer.is_valid():
            validated_data = serializer.validated_data
            members = validated_data.pop('members', [])
            slug = validated_data.get('slug')

            try:
                if not slug:
                    slug = slugify(validated_data['name'], allow_unicode=True)

                board = Board.objects.create(
                    owner=request.user,
                    slug=slug,
                    **validated_data
                )

                if members:
                    board.members.add(*members)

                response_serializer = BoardCreateSerializer(
                    board,
                    context={'request': request}
                )
                return Response(
                    response_serializer.data,
                    status=status.HTTP_201_CREATED
                )

            except Exception as e:
                logger.error(f"Create board failed: {str(e)}", exc_info=True)
                if settings.DEBUG:
                    return Response(
                        {"detail": f"An error occurred: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

