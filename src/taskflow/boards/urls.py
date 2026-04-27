from django.urls import path

from .views import (
    BoardCreateView
)

urlpatterns = [
    path(
        'create/',
        BoardCreateView.as_view(),
        name='board-create'
    )
]