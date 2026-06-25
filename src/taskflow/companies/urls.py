from django.urls import path

from .views import (
    CompanyDetailView,
    CompanyCreateView,
    RequestJoinCompanyView,
    AcceptJoinRequestView,
    RejectJoinRequestView,
    SendMemberInvitationView
)

urlpatterns = [
    path(
        'create/',
        CompanyCreateView.as_view(),
        name='company-create'
    ),
    path(
        'detail/<int:pk>/',
        CompanyDetailView.as_view(),
        name='company-detail'
    ),
    path(
        'invitations/request/join/',
         RequestJoinCompanyView.as_view(),
        name='request-join'
    ),
    path(
        'invitations/<str:token>/accept/',
         AcceptJoinRequestView.as_view(),
        name='approve-request'
    ),
    path(
        'invitations/<str:token>/reject/',
         RejectJoinRequestView.as_view(),
        name='reject-request'
    ),
    path(
        '<int:company_id>/invite-member/',
         SendMemberInvitationView.as_view(),
         name='invite-member'
    ),
]