import logging
from hashlib import md5
import json

from django.core.cache import cache
from django.conf import settings

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Notification
from .paginations import StandardResultsSetPagination
from .filters import NotificationFilter
from .serializers import NotificationListSerializer
from taskflow.accounts.authentication import CookieJWTAuthentication

logger = logging.getLogger(__name__)
CACHE_TTL = getattr(settings, 'CACHE_TTL', 300)


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def get_cache_key(self, request):
        query_params = request.query_params.dict()

        query_params['page'] = request.query_params.get('page', 1)
        query_params['page_size'] = request.query_params.get('page_size', 10)

        sorted_params = sorted(query_params.items())

        params_str = json.dumps(sorted_params, sort_keys=True)
        cache_key = f"notification_list_{md5(params_str.encode()).hexdigest()}"

        return cache_key


    def get(self, request):

        cached_key = self.get_cache_key(request)
        cached_data = cache.get(cached_key)

        if cached_data is not None:
            return Response(
                cached_data,
                status=status.HTTP_200_OK
            )
        try:
            queryset = Notification.objects.filter(
                recipient=request.user
            ).select_related(
                'sender'
            ).only(
                'id', 'title', 'message', 'notification_type',
                'status', 'created_at', 'action_url',
                'sender__id', 'sender__email',
            ).order_by('-created_at')

            filterset = NotificationFilter(request.query_params, queryset=queryset)

            if filterset.is_valid():
                filtered_queryset = filterset.qs
            else:
                filtered_queryset = queryset

            paginator = StandardResultsSetPagination()
            paginator.page_size = request.query_params.get('page_size', 10)

            page = paginator.paginate_queryset(filtered_queryset, request)

            if page is not None:
                serializer = NotificationListSerializer(page, many=True)

                response_data = {
                    'links': {
                        'next': paginator.get_next_link(),
                        'previous': paginator.get_previous_link()
                    },
                    'count': paginator.page.paginator.count,
                    'total_pages': paginator.page.paginator.num_pages,
                    'current_page': paginator.page.number,
                    'results': serializer.data
                }

                cache.set(
                    cached_key,
                    response_data,
                    60 * 15
                )

                return Response(
                    response_data,
                    status=status.HTTP_200_OK
                )

            return Response(
                {"error": "No Notifications found"},
                status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            logger.error(f"Notification List failed: {str(e)}", exc_info=True)
            if settings.DEBUG:
                return Response(
                    {"detail": f"An error occurred: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            return Response(
                {"detail": "Internal Server Error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

