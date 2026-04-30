import logging

from django.db import transaction
from django.utils.text import slugify
from django.conf import settings
from django.core.cache import cache

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Board
from .paginations import StandardResultsSetPagination
from .serializers import (
    BoardCreateSerializer,
    BoardListSerializer
)


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
            slug = validated_data.pop('slug', None)

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

                cache.delete(f'user_owner_boards_{request.user.id}')

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

from django.db import connection, reset_queries
class OwnerBoardListView(APIView):

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get(self, request):

        try:
            cache_key = f'user_owner_boards_{request.user.id}'
            boards = cache.get(cache_key)
            #connection.force_debug_cursor = True
            #reset_queries()
            if boards is None:
                boards = Board.objects.filter(owner=request.user).select_related('owner').distinct()
                #boards_list = list(boards)
                serializer = BoardListSerializer(boards, many=True)
                # print(f"تعداد کویری‌های اجرا شده برای این ویو: {len(connection.queries)}")
                # for q in connection.queries:
                #     print(q['sql'])
                cache.set(cache_key, serializer.data, 60 * 60 * 24)
                return Response(
                    serializer.data,
                    status=status.HTTP_200_OK
                )

            return Response(
                boards,
                status=status.HTTP_200_OK
            )

        except Exception as e:

            logger.error(f"List board failed: {str(e)}", exc_info=True)
            if settings.DEBUG:
                return Response(
                    {"detail": f"An error occurred: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response(
                {"detail": "An internal server error occurred."},
                      status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
