from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularSwaggerView, SpectacularAPIView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('__debug__/', include("debug_toolbar.urls")),

    path('api/users/', include('taskflow.accounts.urls'), name='users'),
    path('api/boards/', include('taskflow.boards.urls'), name='boards'),
    path('api/companies/', include('taskflow.companies.urls'), name='companies'),
    path('api/notifications/', include('taskflow.notifications.urls'), name='notifications'),

    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='swagger-ui'),
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
