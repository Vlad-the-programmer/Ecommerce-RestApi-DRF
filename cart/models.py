from datetime import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal

from rest_framework.exceptions import ValidationError

from .managers import CartManager, CouponManager, CartItemManager, SavedCartManager
from common.models import CommonModel, ItemCommonModel
from .enums import CART_STATUSES


class Coupon(CommonModel):
    """
    Coupon model with relation to Cart to keep track of coupons in the cart.
    """
    objects = CouponManager()

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="coupons",
        db_index=True,
        verbose_name=_("Product"),
        help_text=_("Product this coupon applies to")
    )
    coupon_code = models.CharField(
        max_length=10,
        db_index=True,
        verbose_name=_("Coupon Code")
    )
    is_expired = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("Is Expired")
    )
    discount_amount = models.PositiveIntegerField(
        default=100,
        verbose_name=_("Discount Amount (%)"),
        help_text=_("Discount percentage")
    )
    minimum_amount = models.PositiveIntegerField(
        default=500,
        verbose_name=_("Minimum Amount"),
        help_text=_("Minimum cart amount required to use this coupon")
    )
    expiration_date = models.DateTimeField(
        db_index=True,
        verbose_name=_("Expiration Date")
    )
    usage_limit = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Usage Limit"),
        help_text=_("Maximum number of times this coupon can be used")
    )
    used_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Used Count"),
        help_text=_("Number of times this coupon has been used")
    )

    class Meta:
        db_table = "coupons"
        verbose_name = _("Coupon")
        verbose_name_plural = _("Coupons")
        ordering = ["-expiration_date"]
        indexes = CommonModel.Meta.indexes + [
            # Core manager index pattern
            models.Index(fields=["is_deleted", "is_expired"]),

            # Common lookup patterns
            models.Index(fields=["coupon_code", "is_deleted", "is_expired"]),
            models.Index(fields=["expiration_date", "is_deleted", "is_expired"]),
            models.Index(fields=["product", "is_deleted", "is_expired"]),
            models.Index(fields=["minimum_amount", "is_deleted"]),

            # For reporting and analytics
            models.Index(fields=["used_count", "usage_limit"]),
            models.Index(fields=["date_created", "is_deleted"]),
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
            models.CheckConstraint(
                check=models.Q(discount_amount__gt=0, discount_amount__lte=100),
                name='valid_discount_range'
            ),
            models.CheckConstraint(
                check=(
                        models.Q(expiration_date__gt=models.F('date_created')) |
                        models.Q(expiration_date__isnull=True)
                ),
                name='valid_expiration_date'
            ),
        ]

    def __str__(self):
        return f"{self.coupon_code} - {self.discount_amount}% - {self.expiration_date}"

    def clean(self):
        """Additional validation"""
        super().clean()
        if self.expiration_date and self.expiration_date <= timezone.now():
            raise ValidationError({
                'expiration_date': _("Expiration date must be in the future")
            })
        if self.used_count > self.usage_limit:
            raise ValidationError({
                'used_count': _("Used count cannot exceed usage limit")
            })

    def save(self, *args, **kwargs):
        """Auto-update is_expired on save"""
        if self.expiration_date and self.expiration_date <= timezone.now():
            self.is_expired = True
        super().save(*args, **kwargs)

    def can_be_deleted(self) -> tuple[bool, str]:
        """Check if coupon can be safely deleted"""
        if self.used_count > 0:
            return False, _("Cannot delete coupon that has been used")
        return super().can_be_deleted()

    def increment_usage(self, commit=True):
        """Increment the usage count of the coupon"""
        self.used_count = models.F('used_count') + 1
        if commit:
            self.save(update_fields=['used_count'])

    def is_valid(self, cart_total: float = None) -> bool:
        """Comprehensive validation"""
        if not super().is_valid():
            return False
        if not self.product or not self.product.is_active or self.product.is_deleted:
            return False
        if cart_total is not None and cart_total < self.minimum_amount:
            return False
        return True

    def apply_discount(self, amount: Decimal) -> Decimal:
        """Apply coupon discount to amount"""
        if not self.is_valid(amount):
            raise ValidationError(_("Coupon is not valid for this amount"))
        discount = (amount * Decimal(self.discount_amount / 100)).quantize(Decimal('0.01'))
        return max(amount - discount, Decimal('0.00'))


class Cart(CommonModel):
    objects = CartManager()

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="cart", null=True, blank=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=CART_STATUSES.choices, default=CART_STATUSES.ACTIVE)

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

    def can_be_deleted(self):
        """Check if cart can be safely soft-deleted."""
        if self.status == CART_STATUSES.ACTIVE:
            return False  # Active carts shouldn't be deleted
        if self.cart_items.filter(is_deleted=False).exists():
            return False  # Carts with items shouldn't be deleted
        return True

    def delete(self, *args, **kwargs):
        """Override delete to handle cart deletion logic."""
        if not self.can_be_deleted():
            raise ValidationError(
                _("Cannot delete active cart or cart with items. Please clear cart first.")
            )
        super().delete(*args, **kwargs)

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
    objects = CartItemManager()

    cart = models.ForeignKey(Cart, on_delete=models.PROTECT, related_name="cart_items")

    def __str__(self):
        product_name = getattr(self.product, 'product_name', 'Unknown Product')
        return f"Cart {self.cart.uuid} - Cart Item - {product_name} - {self.quantity}"

    class Meta:
        db_table = "cart_items"
        verbose_name = "Cart Item"
        verbose_name_plural = "Cart Items"
        ordering = ["-date_created"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=["cart", "is_deleted"]),  # Manager pattern
            models.Index(fields=["cart", "product", "is_deleted"]),  # Product's carts by status
            models.Index(fields=["product", "is_deleted"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'product'],
                condition=models.Q(is_deleted=False),
                name='unique_active_product_per_cart'
            ),
        ]

    def clean(self):
        """Validate cart item before saving"""
        super().clean()

        if self.cart.is_deleted:
            raise ValidationError(_("Cannot add items to deleted cart"))

        if self.cart.status != CART_STATUSES.ACTIVE:
            raise ValidationError(_("Cannot add items to inactive cart"))


class SavedCart(CommonModel):
    """
    Saved cart model for users to save their shopping carts for later.
    Normalized design with proper relationships and constraints.
    """
    objects = SavedCartManager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='saved_carts',
        verbose_name=_('User'),
        help_text=_('User who saved this cart')
    )
    name = models.CharField(
        _('Cart Name'),
        max_length=100,
        help_text=_('Descriptive name for the saved cart')
    )
    description = models.TextField(
        _('Description'),
        blank=True,
        null=True,
        help_text=_('Optional description of the saved cart')
    )
    original_cart = models.ForeignKey(
        "cart.Cart",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='saved_versions',
        verbose_name=_('Original Cart'),
        help_text=_('Original cart that was saved')
    )
    is_default = models.BooleanField(
        _('Default Cart'),
        default=False,
        help_text=_('Whether this is the user\'s default saved cart')
    )
    expires_at = models.DateTimeField(
        _('Expires At'),
        null=True,
        blank=True,
        help_text=_('When this saved cart should automatically expire')
    )

    class Meta:
        db_table = 'saved_carts'
        verbose_name = _('Saved Cart')
        verbose_name_plural = _('Saved Carts')
        ordering = ['-date_created']

        constraints = [
            # Ensure only one default cart per user
            models.UniqueConstraint(
                fields=['user', 'is_default'],
                condition=models.Q(is_default=True, is_deleted=False),
                name='unique_default_cart_per_active_user'
            ),
            # Ensure cart names are unique per user
            models.UniqueConstraint(
                fields=['user', 'name'],
                condition=models.Q(is_deleted=False),
                name='unique_cart_name_per_active_user'
            ),
        ]
        indexes = [
            # User-specific queries
            models.Index(fields=['user', 'is_deleted', 'is_active']),
            models.Index(fields=['user', 'is_default']),
            models.Index(fields=['user', 'date_created']),

            # Expiration management
            models.Index(fields=['expires_at', 'is_deleted']),
            models.Index(fields=['is_deleted', 'expires_at']),

            # Combined status and date queries
            models.Index(fields=['is_active', 'is_deleted', 'date_created']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.name}"

    def clean(self):
        """Validate model constraints before saving."""
        from django.core.exceptions import ValidationError

        if self.is_default and SavedCart.objects.filter(
                user=self.user,
                is_default=True,
                is_deleted=False
        ).exclude(pk=self.pk).exists():
            raise ValidationError(_('User can only have one default saved cart.'))

    def save(self, *args, **kwargs):
        """Override save to handle default cart logic."""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def total_items(self):
        """Total number of items in the saved cart."""
        return self.items.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0

    @property
    def total_price(self):
        """Calculate total price of all items in the saved cart."""
        return sum(item.total_price for item in self.items.all())

    def restore_to_cart(self, user):
        """Restore this saved cart to an active cart for the user."""

        # Get or create user's active cart
        cart, created = Cart.objects.get_or_create(
            user=user,
            is_active=True,
            is_deleted=False
        )

        # Clear existing cart items
        cart.items.all().delete()

        # Copy saved cart items to active cart
        for saved_item in self.items.all():
            CartItem.objects.create(
                cart=cart,
                product=saved_item.product,
                quantity=saved_item.quantity,
                price=saved_item.price
            )

        return cart


class SavedCartItem(CommonModel):
    """
    Individual items within a saved cart.
    Normalized to store product snapshot and quantity.
    """
    saved_cart = models.ForeignKey(
        "cart.SavedCart",
        on_delete=models.PROTECT,
        related_name='items',
        verbose_name=_('Saved Cart'),
        help_text=_('Saved cart containing this item')
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name='saved_cart_items',
        verbose_name=_('Product'),
        help_text=_('Product in the saved cart')
    )
    quantity = models.PositiveIntegerField(
        _('Quantity'),
        default=1,
        validators=[MinValueValidator(1)],
        help_text=_('Quantity of the product')
    )
    price = models.DecimalField(
        _('Price at Save'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('Price of the product when cart was saved')
    )
    product_snapshot = models.JSONField(
        _('Product Snapshot'),
        default=dict,
        help_text=_('JSON snapshot of product details at save time')
    )

    class Meta:
        db_table = 'saved_cart_items'
        verbose_name = _('Saved Cart Item')
        verbose_name_plural = _('Saved Cart Items')
        ordering = ['-date_created']

        constraints = [
            # Ensure unique products per saved cart
            models.UniqueConstraint(
                fields=['saved_cart', 'product'],
                condition=models.Q(is_deleted=False),
                name='unique_product_per_active_saved_cart'
            ),
        ]
        indexes = [
            # Cart-item relationships
            models.Index(fields=['saved_cart', 'is_deleted']),
            models.Index(fields=['product', 'is_deleted']),

            # Price and quantity queries
            models.Index(fields=['price']),
            models.Index(fields=['quantity']),

            # Combined cart and status queries
            models.Index(fields=['saved_cart', 'is_active', 'is_deleted']),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity} in {self.saved_cart.name}"

    @property
    def total_price(self):
        """Calculate total price for this cart item."""
        return self.price * self.quantity

    def save(self, *args, **kwargs):
        """Override save to capture product snapshot."""
        if not self.product_snapshot and self.product:
            self.product_snapshot = {
                'name': self.product.name,
                'sku': self.product.sku,
                'regular_price': str(self.product.regular_price),
                'sale_price': str(self.product.sale_price) if self.product.sale_price else None,
                'image_url': self.product.get_primary_image_url(),
                'category': self.product.category.name if self.product.category else None,
            }
        super().save(*args, **kwargs)