from rest_framework.routers import DefaultRouter
from .views import ShippingClassViewSet


router = DefaultRouter()
router.register(r'shipping', ShippingClassViewSet, basename='shipping')
