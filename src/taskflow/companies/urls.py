from django.urls import path

from .views import CompanyDetailView

urlpatterns = [
    path(
        'detail/<int:pk>/',
        CompanyDetailView.as_view(),
        name='company-detail'
    ),
]