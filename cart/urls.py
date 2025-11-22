from rest_framework.routers import DefaultRouter
from . import views


app_name = 'cart'


router = DefaultRouter()
router.register(r'carts', views.CartViewSet, basename='cart')
router.register(r'cart-items', views.CartItemViewSet, basename='cart-item')
router.register(r'coupons', views.CouponViewSet, basename='coupon')
router.register(r'saved-carts', views.SavedCartViewSet, basename='saved-cart')
router.register(r'saved-cart-items', views.SavedCartItemViewSet, basename='saved-cart-item')

