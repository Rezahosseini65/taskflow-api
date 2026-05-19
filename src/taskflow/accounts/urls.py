from django.urls import path

from .views import (
    UserRegisterView,
    UserLoginView,
    RefreshAccessTokenView,
    UserLogoutView,
    UserUpdateView
)


urlpatterns = [
    path(
        'register/', UserRegisterView.as_view(),
        name='user-register'
    ),
    path(
        'login/', UserLoginView.as_view(),
        name='user-login'
    ),
    path(
        'logout/',
        UserLogoutView.as_view(),
        name='user-logout'
    ),
    path(
        'update/',
        UserUpdateView.as_view(),
        name='user-update'
    ),
    path(
        'token/refresh/',
        RefreshAccessTokenView.as_view(),
        name='token_refresh'
    ),

]