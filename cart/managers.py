from datetime import timedelta

from django.db import models
from django.utils import timezone
from .enums import CART_STATUSES
from common.managers import SoftDeleteManager


class CartManager(SoftDeleteManager):
    """
    Manager for Cart model that excludes deleted carts by default
    and provides cart-specific query methods.
    """

    def active(self):
        """Get active carts (default for most operations)"""
        return self.get_queryset().filter(status=CART_STATUSES.ACTIVE)

    def abandoned(self, days_old=7):
        """Get abandoned carts (older than specified days)"""
        cutoff_date = timezone.now() - timedelta(days=days_old)
        return self.get_queryset().filter(
            status=CART_STATUSES.ACTIVE,
            date_updated__lt=cutoff_date
        )

    def by_user(self, user):
        """Get carts for specific user"""
        return self.get_queryset().filter(user=user)

    def completed(self):
        """Get completed/paid carts"""
        return self.get_queryset().filter(status=CART_STATUSES.PAID)

    def with_items_count(self):
        """Annotate carts with items count"""
        return self.get_queryset().annotate(
            items_count=models.Count('cart_items', filter=models.Q(cart_items__is_deleted=False))
        )


class CouponManager(SoftDeleteManager):
    """
    Manager for Coupon model that excludes deleted and expired coupons by default.
    """

    def get_queryset(self):
        return super().get_queryset().filter(
            is_deleted=False,
            is_expired=False,
            expiration_date__gt=timezone.now()
        )

    def valid_for_amount(self, amount):
        """Get coupons valid for specified cart amount"""
        return self.get_queryset().filter(minimum_amount__lte=amount)

    def by_code(self, code):
        """Get coupon by code (case-insensitive)"""
        return self.get_queryset().filter(coupon_code__iexact=code).first()


class CartItemManager(SoftDeleteManager):
    """
    Manager for CartItem model with item-specific methods.
    """

    def for_cart(self, cart_id):
        """Get all items for specific cart"""
        return self.get_queryset().filter(cart_id=cart_id)

    def for_product(self, product_id):
        """Get all cart items for specific product"""
        return self.get_queryset().filter(product_id=product_id)

    def with_product_details(self):
        """Annotate with product details"""
        return self.get_queryset().select_related('product')


class SavedCartManager(SoftDeleteManager):
    """
    Manager for SavedCart model with saved cart specific methods.
    """

    def for_user(self, user):
        """Get all saved carts for user"""
        return self.get_queryset().filter(user=user)

    def default_for_user(self, user):
        """Get user's default saved cart"""
        return self.get_queryset().filter(user=user, is_default=True).first()

    def expired(self):
        """Get expired saved carts"""
        return self.get_queryset().filter(expires_at__lt=timezone.now())

    def with_items_count(self):
        """Annotate with items count"""
        return self.get_queryset().annotate(
            items_count=models.Count('items', filter=models.Q(items__is_deleted=False))
        )