from django.urls import path

from .views import (
    CompanyDetailView,
    CompanyCreateView,
    RequestJoinCompanyView,
    ApproveJoinRequestView,
    RejectJoinRequestView
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
        'invitation/request-join/',
         RequestJoinCompanyView.as_view(),
        name='request-join'
    ),
    path(
        'invitations/<int:invitation_id>/approve/',
         ApproveJoinRequestView.as_view(),
        name='approve-request'
    ),
    path(
        'invitations/<int:invitation_id>/reject/',
         RejectJoinRequestView.as_view(),
        name='reject-request'
    ),
]