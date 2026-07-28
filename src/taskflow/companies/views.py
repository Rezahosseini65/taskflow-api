import logging

from django.db.models import Q, Exists, OuterRef
from django.core.cache import cache
from django.db import transaction, IntegrityError, DatabaseError
from django.conf import settings

from rest_framework.generics import get_object_or_404
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Company, Membership, Invitation
from .tasks import (
    create_join_request_task,
    accept_invitation_task,
    reject_invitation_task,
    create_member_invitation_task, member_accept_invitation_task
)
from .serializers import (
    CompanyDetailSerializer,
    CompanyCreateSerializer,
    RequestJoinCompanySerializer,
    SendMemberInvitationSerializer
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
            name = validated_data.pop('name')
            members = validated_data.pop('members', [])
            slug = validated_data.pop('slug')  # حالا slug در validated_data وجود دارد

            try:
                company = Company.objects.create(
                    name=name.lower(),
                    owner=request.user,
                    slug=slug,
                    **validated_data
                )

                Membership.objects.create(
                    user=request.user,
                    company=company,
                    role=Membership.RoleChoices.OWNER
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


class RequestJoinCompanyView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def post(self, request):
        user = request.user
        serializer = RequestJoinCompanySerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        company_name = serializer.validated_data['company_name']

        company = Company.objects.filter(
            name=company_name.lower(),
            is_active=True
        ).annotate(
            is_member=Exists(
                Membership.objects.filter(user=user, company_id=OuterRef("id"))
            ),
            has_pending_request=Exists(
                Invitation.objects.filter(
                    email=user.email,
                    company_id=OuterRef('id'),
                    status=Invitation.InvitationStatus.PENDING,
                    invitation_type=Invitation.InvitationType.REQUEST
                )
            )
        ).only('id', 'email').first()

        if not company:
            return Response(
                {"error":"Company does not exist or is not active."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if company.is_member:
            return Response(
                {"error":"You are already a member of this company"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if company.has_pending_request:
            return Response(
                {"error":"You already have a pending join request"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            task = create_join_request_task.delay(
                company_name=company_name,
                user_id=request.user.id,
                message=serializer.validated_data.get('message', '')
            )

            return Response({
                'task_id': task.id,
                'status': task.status,
                'message': 'Join request is being processed asynchronously'
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            return Response({
                'success': False,
                'error': str(e) if settings.DEBUG else 'Join request failed'
            }, status=status.HTTP_400_BAD_REQUEST)


class AcceptJoinRequestView(APIView):
    """
    Accept a join request invitation.
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def post(self, request, token):
        try:
            # Execute task asynchronously
            task = accept_invitation_task.delay(token, request.user.id)

            return Response({
                'status': 'processing',
                'task_id': task.id,
                'message': 'Join request is being processed',
                'detail': 'Join request is being processed asynchronously',
                'token': token
            }, status=status.HTTP_202_ACCEPTED)

        except PermissionError as e:
            return Response({
                'status': 'error',
                'error': 'permission_denied',
                'message': 'You do not have permission to approve this request',
                'detail': str(e)
            }, status=status.HTTP_403_FORBIDDEN)

        except ValueError as e:
            # Validation error (e.g., expired invitation)
            error_message = str(e)

            if 'expired' in error_message.lower():
                return Response({
                    'status': 'error',
                    'error': 'invitation_expired',
                    'message': 'The join request link has expired',
                    'detail': error_message
                }, status=status.HTTP_400_BAD_REQUEST)
            elif 'already' in error_message.lower():
                return Response({
                    'status': 'error',
                    'error': 'already_processed',
                    'message': 'This request has already been processed',
                    'detail': error_message
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({
                    'status': 'error',
                    'error': 'validation_error',
                    'message': 'Invalid request data',
                    'detail': error_message if settings.DEBUG else None
                }, status=status.HTTP_400_BAD_REQUEST)

        except Invitation.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'invitation_not_found',
                'message': 'Join request not found',
                'detail': 'The invitation does not exist or has been removed'
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            # Unexpected error
            logger.exception(f"Unexpected error in AcceptJoinRequestView: {str(e)}")

            return Response({
                'status': 'error',
                'error': 'internal_server_error',
                'message': 'An unexpected error occurred. Please try again.',
                'detail': str(e) if settings.DEBUG else None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RejectJoinRequestView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def post(self, request, token):
        reason = request.data.get('reason', '')

        try:
            # Execute task asynchronously
            task = reject_invitation_task.delay(
                token,
                request.user.id,
                reason
            )

            return Response({
                'status': 'processing',
                'task_id': task.id,
                'message': 'Join request is being processed',
                'detail': 'Join request is being processed asynchronously',
                'token': token
            }, status=status.HTTP_202_ACCEPTED)

        except PermissionError as e:
            return Response({
                'status': 'error',
                'error': 'permission_denied',
                'message': 'You do not have permission to reject this request',
                'detail': str(e)
            }, status=status.HTTP_403_FORBIDDEN)

        except ValueError as e:
            # Validation error (e.g., expired invitation)
            error_message = str(e)

            if 'expired' in error_message.lower():
                return Response({
                    'status': 'error',
                    'error': 'invitation_expired',
                    'message': 'The join request link has expired',
                    'detail': error_message
                }, status=status.HTTP_400_BAD_REQUEST)
            elif 'already' in error_message.lower():
                return Response({
                    'status': 'error',
                    'error': 'already_processed',
                    'message': 'This request has already been processed',
                    'detail': error_message
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({
                    'status': 'error',
                    'error': 'validation_error',
                    'message': 'Invalid request data',
                    'detail': error_message if settings.DEBUG else None
                }, status=status.HTTP_400_BAD_REQUEST)

        except Invitation.DoesNotExist:
            return Response({
                'status': 'error',
                'error': 'invitation_not_found',
                'message': 'Join request not found',
                'detail': 'The invitation does not exist or has been removed'
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            # Unexpected error
            logger.exception(f"Unexpected error in RejectJoinRequestView: {str(e)}")

            return Response({
                'status': 'error',
                'error': 'internal_server_error',
                'message': 'An unexpected error occurred. Please try again.',
                'detail': str(e) if settings.DEBUG else None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SendMemberInvitationView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def post(self, request, company_id):

        try:
            company = Company.objects.select_related('owner').only(
                'id', 'name', 'is_active', 'owner_id',
                'owner__id', 'owner__email'
            ).get(id=company_id, is_active=True)

        except Company.DoesNotExist as e:
            logger.warning(f"Company {company_id} not found: {e}")
            return Response(
                {'error': 'Company not found or inactive'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not Membership.objects.filter(
                user=request.user,
                company=company,
                role__in=[Membership.RoleChoices.ADMIN, Membership.RoleChoices.OWNER]
        ).only('id').exists():
            logger.warning(f"User {request.user.id} tried to invite without permission")
            return Response(
                {'error': 'You do not have permission to invite members'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = SendMemberInvitationSerializer(
            data=request.data,
            context={
                'company': company,
                'inviter': request.user
            }
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        invited_user = serializer.context.get('invited_user')
        role = serializer.validated_data.get(
            'role',
            Membership.RoleChoices.MEMBER
        )

        try:
            task = create_member_invitation_task.delay(
                company_id=company.id,
                invited_user_id=invited_user.id,
                inviter_id=request.user.id,
                role=role
            )

            return Response({
                'status': 'processing',
                'task_id': task.id,
                'message': 'Send member invitation is being processed',
                'detail': 'Send member invitation is being processed asynchronously',
            }, status=status.HTTP_201_CREATED)

        except IntegrityError as e:
            logger.error(f"Integrity error: {e}", exc_info=True)
            return Response(
                {
                    'error': 'Database integrity error',
                    'code': 'INTEGRITY_ERROR'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        except DatabaseError as e:
            logger.error(f"Database error: {e}", exc_info=True)
            return Response(
                {
                    'error': 'Database error occurred',
                    'code': 'DATABASE_ERROR'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        except Exception as e:
            logger.error(f"Failed to create task: {e}", exc_info=True)
            return Response(
                {
                    'error': 'Failed to send invitation',
                    'code': 'TASK_FAILED'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MemberAcceptInvitationView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]

    def post(self, request, token):

        try:
            invitation = Invitation.objects.get(
                token=token,
                status=Invitation.InvitationStatus.PENDING,
            )
        except Invitation.DoesNotExist:
            return Response(
                {"error": "Invitation not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            task = member_accept_invitation_task.delay(
                token,
                request.user.id,
            )

            return Response(
                {
                    "status": "processing",
                    "message": "Invitation acceptance is being processed",
                    "task_id": task.id,
                    "token": token,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except IntegrityError:
            return Response(
                {
                    "error": "Database integrity error",
                    "code": "INTEGRITY_ERROR",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        except DatabaseError:
            return Response(
                {
                    "error": "Database error occurred",
                    "code": "DATABASE_ERROR",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        except Exception:
            return Response(
                {
                    "error": "Failed to process invitation",
                    "code": "TASK_FAILED",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
