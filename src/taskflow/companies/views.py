import logging

from django.db.models import Q, Exists, OuterRef
from django.core.cache import cache
from django.db import transaction
from django.utils.text import slugify
from django.conf import settings

from rest_framework.generics import get_object_or_404
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Company, Membership
from .serializers import (
    CompanyDetailSerializer,
    CompanyCreateSerializer
)

from taskflow.accounts.authentication import CookieJWTAuthentication


logger = logging.getLogger(__name__)


class CompanyCreateView(APIView):

    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    @transaction.atomic
    def post(self, request):
        serializer = CompanyCreateSerializer(
            data=request.data,
            context={'request':request}
        )
        if serializer.is_valid():
            validated_data = serializer.validated_data
            members = validated_data.pop('members', [])
            slug = validated_data.pop('slug', None)

            try:
                if not slug:
                    slug = slugify(validated_data['name'], allow_unicode=True)

                company = Company.objects.create(
                    owner=request.user,
                    slug=slug,
                    **validated_data
                )

                Membership.objects.create(
                    user=request.user,
                    company=company,
                    role=Membership.RoleChoices.ADMIN
                )

                if members:
                    for member in members:
                        if member != request.user:
                            Membership.objects.create(
                                user=member,
                                company=company,
                                role=Membership.RoleChoices.MEMBER
                            )

                responses_serializer = CompanyCreateSerializer(
                    company,
                    context={'request':request}
                )

                return Response(
                    responses_serializer.data,
                    status=status.HTTP_201_CREATED
                )

            except Exception as e:
                logger.error(f"Create Company failed: {str(e)}", exc_info=True)
                if settings.DEBUG:
                    return Response(
                        {"detail": f"An error occurred: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                return Response(
                    {'detail':'Server Error'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


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
                Q(owner=request.user) |
                Q(Exists(Membership.objects.filter(
                    company_id=OuterRef('id'),
                    user=request.user
                ))),
                pk=pk
            )
            .select_related('owner')
            .only(
                'id', 'name', 'slug', 'email', 'website',
                'description', 'logo', 'is_active',
                'created_at', 'updated_at',
                'owner__id', 'owner__email'
            )
        )

        serializer = CompanyDetailSerializer(company)

        cache.set(cache_key, serializer.data, 60 * 15)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )