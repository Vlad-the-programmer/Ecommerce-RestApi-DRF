from .enums import CART_STATUSES
from common.managers import SoftDeleteManger


class CartManager(SoftDeleteManger):
    """Default queryset excludes soft deleted carts and paid carts."""
    def get_queryset(self):
        return super().get_queryset().filter(status=CART_STATUSES.ACTIVE)

class NonExpiredOrDeletedCouponManager(SoftDeleteManger):
    """Default queryset excludes soft deleted coupons and expired coupons."""
    def get_queryset(self):
        return super().get_queryset().filter(is_expired=False)

class CartItemManager(SoftDeleteManger):
    """Default queryset includes active cart items."""
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


