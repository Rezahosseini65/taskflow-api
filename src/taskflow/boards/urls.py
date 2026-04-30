from django.urls import path

from .views import (
    BoardCreateView,
    OwnerBoardListView
)

urlpatterns = [
    path(
        'create/',
        BoardCreateView.as_view(),
        name='board-create'
    ),
    path(
        'owned/list/',
        OwnerBoardListView.as_view(),
        name='board-owned-list'
    )
]