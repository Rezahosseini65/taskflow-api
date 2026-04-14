from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularSwaggerView, SpectacularAPIView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='swagger-ui'),
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
]
