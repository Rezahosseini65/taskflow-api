from django.urls import path

from .views import UserRegisterView, UserLoginView, RefreshAccessTokenView


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
        'token/refresh/',
        RefreshAccessTokenView.as_view(),
        name='token_refresh'
    ),
]