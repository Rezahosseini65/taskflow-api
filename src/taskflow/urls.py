from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularSwaggerView, SpectacularAPIView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/users/', include('taskflow.accounts.urls'), name='register-user'),
    path('api/boards/', include('taskflow.boards.urls'), name='create-board'),

    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='swagger-ui'),
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
]
