from django.urls import path

from .views import (
    BoardCreateView,
    OwnerBoardListView,
    OwnerBoardDetailView,
    MemberBoardListView,
    MemberBoardDetailView
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
    ),
    path(
        'owned/detail/<int:pk>/',
        OwnerBoardDetailView.as_view(),
        name='board-owned-detail'
    ),
    path(
        'member/list/',
        MemberBoardListView.as_view(),
        name='board-member-list'
    ),
    path(
        'member/detail/<int:pk>/',
        MemberBoardDetailView.as_view(),
        name='board-member-detail'
    )
]