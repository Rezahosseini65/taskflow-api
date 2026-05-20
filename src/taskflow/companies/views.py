from django.db.models import Prefetch, Q
from django.core.cache import cache

from rest_framework.generics import get_object_or_404
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Company
from .serializers import CompanyDetailSerializer
from taskflow.accounts.authentication import CookieJWTAuthentication
from taskflow.accounts.models import CustomUser


class CompanyDetailView(APIView):

    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def get_cache_key(self, user_id:int, company_pk:int)-> str:
        return f'company_detail_{company_pk}_user_{user_id}'

    def get(self, request, pk):

        cache_key = self.get_cache_key(request.user.id, pk)
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            return Response(
                cached_data,
                status=status.HTTP_200_OK
            )

        company = get_object_or_404(
            Company.objects.filter(
                Q(owner=request.user) | Q(members=request.user)
            ).distinct()
            .select_related('owner').only(
                    'id', 'name', 'slug', 'email', 'website',
                    'description', 'logo', 'owner', 'is_active',
                    'created_at', 'updated_at',
                    'owner__id', 'owner__email'
            ).prefetch_related(
                Prefetch(
                    'members',
                    queryset=CustomUser.objects.only('id', 'email')
                )
            ),
            pk=pk
        )

        serializer = CompanyDetailSerializer(company)

        cache.set(cache_key, serializer.data, 60 * 15)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )