import logging

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404
from django.utils.text import slugify
from django.conf import settings
from django.core.cache import cache

from rest_framework.generics import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Board
from .paginations import StandardResultsSetPagination
from .serializers import (
    BoardCreateSerializer,
    BoardListSerializer,
    BoardDetailSerializer
)
from taskflow.accounts.models import CustomUser


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

    def get(self, request):

        try:
            cache_key = f'user_owner_boards_{request.user.id}'
            boards = cache.get(cache_key)
            #connection.force_debug_cursor = True
            #reset_queries()
            if boards is None:
                boards = Board.objects.filter(owner=request.user, is_active=True)\
                         .select_related('owner') \
                         .only('id', 'name', 'slug', 'created_at', 'owner__id', 'owner__email')
                #boards_list = list(boards)
                serializer = BoardListSerializer(boards, many=True)
                # print(f"تعداد کویری‌های اجرا شده برای این ویو: {len(connection.queries)}")
                # for q in connection.queries:
                #     print(q['sql'])
                cache.set(cache_key, serializer.data, 60 * 60 * 15)
                return Response(
                    serializer.data,
                    status=status.HTTP_200_OK
                )

            return Response(
                boards,
                status=status.HTTP_200_OK
            )

        except Exception as e:

            logger.error(f"Owner List board failed: {str(e)}", exc_info=True)
            if settings.DEBUG:
                return Response(
                    {"detail": f"An error occurred: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response(
                {"detail": "An internal server error occurred."},
                      status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class OwnerBoardDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def get_cache_key(self, user_id, board_pk):
        return f'owner_board_detail_{board_pk}_user_{user_id}'

    def get(self, request, pk):
        cache_key = self.get_cache_key(request.user.id, pk)
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        board = get_object_or_404(
            Board.objects
            .filter(owner=request.user, is_active=True)
            .select_related('owner')
            .only(
                'id', 'name', 'slug', 'description', 'created_at','updated_at',
                'owner__id', 'owner__email'
            ).prefetch_related(
                Prefetch('members',
                         queryset=CustomUser.objects.only('id', 'email'))
            ),
            pk=pk
        )

        serializer = BoardDetailSerializer(board)
        cache.set(cache_key, serializer.data, 60 * 15)

        return Response(serializer.data, status=status.HTTP_200_OK)


class MemberBoardListView(APIView):

    permission_classes = [IsAuthenticated]

    def get_cache_key(self, user_id):
        return f'member_board_list_user_{user_id}'

    def get(self, request):
        cache_key = self.get_cache_key(request.user.id)
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(
                cached_data,
                status=status.HTTP_200_OK
            )
        try:
            boards = Board.objects.filter(members=request.user, is_active=True) \
                .exclude(owner=request.user) \
                .select_related("owner") \
                .only('id', 'name', 'slug', 'created_at', 'owner__id', 'owner__email')

            serializer = BoardListSerializer(boards, many=True)

            cache.set(cache_key, serializer.data, 60 * 15)

            return Response(
                serializer.data,
                status=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"Member List board failed: {str(e)}", exc_info=True)
            if settings.DEBUG:
                return Response(
                    {"detail": f"An error occurred: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response(
                {"detail": "An internal server error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MemberBoardDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def get_cache_key(self, user_id:int, board_pk:int)-> str:
        return f'member_board_detail_{board_pk}_user_{user_id}'

    def get(self, request, pk):
        try:
            cache_key = self.get_cache_key(request.user.id, pk)
            cached_data = cache.get(cache_key)

            if cached_data is not None:
                return Response(
                    cached_data,
                    status=status.HTTP_200_OK
                )

            board = get_object_or_404(
                Board.objects.filter(
                    Q(members=request.user) & ~Q(owner=request.user) & Q(is_active=True)
                ).select_related(
                    'owner'
                ).only(
                    'id', 'name', 'slug', 'description', 'created_at', 'updated_at',
                    'owner__id', 'owner__email'
                ).prefetch_related(
                    Prefetch(
                        'members',
                        queryset=CustomUser.objects.only('id', 'email')
                    )
                ),
                pk=pk
            )

            serializer = BoardDetailSerializer(board)

            cache.set(cache_key, serializer.data, 60 * 15)

            return Response(
                serializer.data,
                status=status.HTTP_200_OK
            )
        except Http404:
            return Response(
                {"detail": "Board not found or you don't have access."},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            logger.error(f"Member Detail board failed: {str(e)}", exc_info=True)
            if settings.DEBUG:
                return Response(
                    {"detail": f"An error occurred: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response(
                {"detail": "An internal server error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
