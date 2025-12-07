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
from rest_framework.routers import DefaultRouter

# Routers
from cart.urls import router as cart_router
from category.urls import router as category_router
from products.urls import router as product_router
from orders.urls import router as order_router
from payments.urls import router as payment_router
from reviews.urls import router as review_router
from invoices.urls import router as invoice_router
from refunds.urls import router as refund_router
from wishlist.urls import router as wishlist_router
from shipping.urls import router as shipping_router


urlpatterns = [
    path('admin/', admin.site.urls),

    path('accounts/', include('allauth.urls')),

    path('api/auth/', include('userAuth.urls')),

    path('api/schema/', SpectacularAPIView.as_view(api_version='v1'), name='schema'),

    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    path('api/schema/redoc/',
         SpectacularRedocView.as_view(
             url_name='schema',
             url='/api/schema/',
         ),
         name='redoc'
         ),

    path('', RedirectView.as_view(url='/api/schema/swagger-ui/', permanent=False)),
]


v1_router = DefaultRouter()

v1_router.registry.extend(cart_router.registry)
v1_router.registry.extend(category_router.registry)
v1_router.registry.extend(product_router.registry)
v1_router.registry.extend(order_router.registry)
v1_router.registry.extend(payment_router.registry)
v1_router.registry.extend(review_router.registry)
v1_router.registry.extend(invoice_router.registry)
v1_router.registry.extend(refund_router.registry)
v1_router.registry.extend(wishlist_router.registry)
v1_router.registry.extend(shipping_router.registry)


v1_urls = [
    path('api/v1/admin/store-management/', include('inventory.urls')),
    path('api/v1/profile/', include('users.urls')),
] + v1_router.urls


urlpatterns += [
    path('api/v1/', include((v1_urls, 'v1'), namespace='v1')),
]


if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    try:
        import debug_toolbar

        urlpatterns = [
                          path('__debug__/', include(debug_toolbar.urls)),
                      ] + urlpatterns
    except ImportError:
        pass