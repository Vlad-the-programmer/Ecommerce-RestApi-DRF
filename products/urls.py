from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, ProductVariantViewSet, ProductImageViewSet, LocationViewSet

app_name = 'products'


router = DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'product-variants', ProductVariantViewSet)
router.register(r'product-images', ProductImageViewSet)
router.register(r'locations', LocationViewSet)

urlpatterns = router.urls