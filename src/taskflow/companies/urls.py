from django.urls import path

from .views import (
    CompanyDetailView,
    CompanyCreateView,
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
]