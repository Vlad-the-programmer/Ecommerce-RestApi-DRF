from cart.models import CART_STATUSES
from common.managers import NonDeletedObjectsManager


class CartManager(NonDeletedObjectsManager):
    """Default queryset excludes soft deleted carts and paid carts."""
    def get_queryset(self):
        return super().get_queryset().filter(status=CART_STATUSES.ACTIVE)

class NonExpiredOrDeletedCouponManager(NonDeletedObjectsManager):
    """Default queryset excludes soft deleted coupons and expired coupons."""
    def get_queryset(self):
        return super().get_queryset().filter(is_expired=False)

