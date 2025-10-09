from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

# API Schema
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

# Import settings
from django.conf import settings

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API Schema - JSON
    path('api/schema/', SpectacularAPIView.as_view(api_version='v1'), name='schema'),

    # Swagger UI
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # ReDoc UI
    path('api/schema/redoc/',
         SpectacularRedocView.as_view(
             url_name='schema',
             url='/api/schema/',
         ),
         name='redoc'
         ),

    # Add a redirect from / to /api/schema/swagger-ui/
    path('', RedirectView.as_view(url='/api/schema/swagger-ui/', permanent=False)),

    # API Endpoints
    path('api/profile/', include('users.urls')),
    path('api/auth/', include('userAuth.urls')),

    # Allauth URLs (for email verification)
    path('accounts/', include('allauth.urls')),

]

# Serve media and static files in development
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    # Serve static files
    urlpatterns += staticfiles_urlpatterns()

    # Serve media files
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Debug toolbar
    try:
        import debug_toolbar

        urlpatterns = [
                          path('__debug__/', include(debug_toolbar.urls)),
                      ] + urlpatterns
    except ImportError:
        pass