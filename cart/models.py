from datetime import datetime

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .managers import CartManager, NonExpiredOrDeletedCouponManager
from common.models import CommonModel, ItemCommonModel
from .enums import CART_STATUSES


class Coupon(CommonModel):
    """
    Coupon model with relation to Cart to keep track of coupons in the cart.
    """
    objects = NonExpiredOrDeletedCouponManager()

    coupon_code = models.CharField(max_length=10)
    is_expired = models.BooleanField(default=False)
    discount_amount = models.PositiveIntegerField(default=100, help_text=_("Discount in %(s)"))
    minimum_amount = models.PositiveIntegerField(default=500, help_text=_("Minimum amount required to use this coupon"))
    expiration_date = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(default=1, help_text=_("Number of times this coupon can be used"))
    used_count = models.PositiveIntegerField(default=0, help_text=_("Number of times this coupon has been used"))

    def __str__(self):
        return f"{self.coupon_code} - {self.discount_amount}% - {self.expiration_date} - Expired: {self.is_expired}"

    class Meta:
        db_table = "coupons"
        verbose_name = "Coupon"
        verbose_name_plural = "Coupons"
        ordering = ["-expiration_date"]
        indexes = CommonModel.Meta.indexes + [
            # Core manager index pattern
            models.Index(fields=["is_deleted", "is_expired"]),  # For NonExpiredOrDeletedCouponManager

            # Common lookup patterns
            models.Index(fields=["coupon_code", "is_deleted", "is_expired"]),  # Code validation
            models.Index(fields=["expiration_date", "is_deleted", "is_expired"]),  # Cleanup queries
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['coupon_code'],
                name='unique_coupon_code',
                condition=models.Q(is_deleted=False)
            ),
            models.CheckConstraint(
                check=models.Q(usage_limit__gte=1),
                name='usage_limit_check'
            ),
        ]

    def is_valid(self):
        """Comprehensive validation"""
        if self.is_expired:
            return False
        if datetime.now() > self.expiration_date:
            return False
        if self.used_count >= self.usage_limit:
            return False
        return True

    def check_cart_qualifies_for_coupon(self, cart_total: float):
        """Check if cart qualifies for coupon"""
        return self.is_valid() and cart_total >= self.minimum_amount


class Cart(CommonModel):
    objects = CartManager()

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="cart", null=True, blank=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=CART_STATUSES, default=CART_STATUSES.ACTIVE)

    def __str__(self):
        return f"Cart {self.id}"

    class Meta:
        db_table = "carts"
        verbose_name = "Cart"
        verbose_name_plural = "Carts"
        ordering = ["-date_created"]
        indexes = CommonModel.Meta.indexes + [
            # Status-based indexes
            models.Index(fields=["status"]),
            models.Index(fields=["is_deleted", "status"]),  # Manager pattern
            models.Index(fields=["user", "is_deleted", "status"]),  # User's carts by status
            models.Index(fields=["date_created", "is_deleted", "status"]),  # Recent carts by status

            # Analytics indexes
            models.Index(fields=["status", "date_created"]),  # Status changes over time
        ]


    def get_cart_total(self):
        cart_items = self.cart_items.all()
        total_price = 0

        for cart_item in cart_items:
            total_price += cart_item.get_total_cart_item_price()

        return total_price

    def get_cart_total_price_after_coupon(self):
        """Calculate total price after applying coupon"""
        total = self.get_cart_total()

        if self.coupon and self.coupon.is_valid(total):
            discount = (total * self.coupon.discount_amount) / 100
            total -= discount

        return max(total, 0)  # Ensure non-negative total


class CartItem(ItemCommonModel):
    """
    CartItem model with relation to Cart to keep track of items in the cart.
    """
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="cart_items")

    def __str__(self):
        product_name = getattr(self.product, 'product_name', 'Unknown Product')
        return f"Cart {self.cart.uuid} - Cart Item - {product_name} - {self.quantity}"

    class Meta:
        db_table = "cart_items"
        verbose_name = "Cart Item"
        verbose_name_plural = "Cart Items"
        ordering = ["-date_created"]
        indexes = [
            models.Index(fields=["cart", "is_deleted"]),  # Manager pattern
            models.Index(fields=["cart", "product", "is_deleted"]),  # Product's carts by status
        ]