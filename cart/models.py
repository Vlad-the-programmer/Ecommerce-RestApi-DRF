import logging
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

logger = logging.getLogger(__name__)


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
        if not super().can_be_deleted()[0]:
            return False, super().can_be_deleted()[1]

        if self.used_count > 0:
            return False, _("Cannot delete coupon that has been used")
        return True, ""

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
            logger.debug(f"Product for this product is {self.product or "None"} and Active: {self.product.is_active} \
                            Deleted: {self.product.is_deleted}")
            return False
        if cart_total is not None and cart_total < self.minimum_amount:
            logger.debug(f"Coupon validation failed: cart_total ({cart_total}) is less \ "
                         f"than minimum_amount ({self.minimum_amount})")
            return False
        return True

    def apply_discount(self, amount: Decimal) -> Decimal:
        """Apply coupon discount to amount"""
        if not self.is_valid(float(amount)):
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
        if not super().can_be_deleted()[0]:
            return False, super().can_be_deleted()[1]

        if self.status == CART_STATUSES.ACTIVE:
            return False,  "Active carts shouldn't be deleted"
        if self.cart_items.filter(is_deleted=False).exists():
            return False,  "Carts with items shouldn't be deleted"
        return True, ""

    def is_valid(self, *args, **kwargs) -> bool:
        """
        Check if the cart is valid by verifying:
        1. Parent class validation (is_active, is_deleted, etc.)
        2. Cart status is valid
        3. All cart items are valid
        4. If a coupon is applied, it's still valid
        """
        # Check parent class validation
        if not super().is_valid():
            return False
        
        # Check if cart status is valid
        if self.status not in dict(CART_STATUSES.choices):
            return False
        
        # Check if all cart items are valid
        if not self.cart_items.filter(is_deleted=False).exists():
            return False
        
        # Check each cart item's validity
        for item in self.cart_items.filter(is_deleted=False):
            if not item.is_valid():
                return False
        
        # If there's a coupon, validate it
        if self.coupon:
            if not self.coupon.is_valid(self.get_cart_total()):
                return False
        
        return True

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

    def is_valid(self, *args, **kwargs) -> bool:
        """Check if the cart item is valid by verifying:
        1. Parent class validation (is_active, is_deleted, etc.)
        2. Cart is valid and active
        3. Product is valid and available
        4. Quantity is valid
        5. Variant (if any) is valid

        Returns:
            bool: True if the cart item is valid, False otherwise.
        """
        # Check parent class validation
        if not super().is_valid():
            return False

        # Check if cart is valid
        if not hasattr(self, 'cart') or not self.cart or self.cart.is_deleted:
            return False
            
        # Check if cart is active
        if self.cart.status != CART_STATUSES.ACTIVE:
            return False
            
        # Check if product exists and is valid
        if not self.product or not self.product.is_valid():
            return False
            
        # Check if variant exists and is valid (if specified)
        if hasattr(self, 'variant') and self.variant and \
           (not hasattr(self.variant, 'is_valid') or not self.variant.is_valid()):
            return False
            
        # Check if quantity is valid
        if self.quantity < 1:
            return False
            
        # Check if product is in stock
        if hasattr(self.product, 'is_in_stock') and not self.product.is_in_stock():
            return False
            
        # Check if variant is in stock (if specified)
        if hasattr(self, 'variant') and self.variant and \
           hasattr(self.variant, 'is_in_stock') and not self.variant.is_in_stock():
            return False
            
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """Check if cart item can be safely soft-deleted.
        
        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        # Check parent class validation
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason
            
        # Check if cart exists and is valid
        if not hasattr(self, 'cart') or not self.cart:
            return True, ""
            
        # Check if cart is in a state that allows item deletion
        if self.cart.status != CART_STATUSES.ACTIVE:
            return False, "Cannot delete items from an inactive cart"
            
        # Check if there are any associated orders that prevent deletion
        if hasattr(self, 'order_items') and hasattr(self.order_items, 'exists') and self.order_items.exists():
            return False, "Cannot delete cart item associated with an order"
            
        return True, ""


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
                fields=['user'],
                condition=models.Q(is_default=True, is_deleted=False),
                name='unique_default_saved_cart_per_user',
                violation_error_message=_('User can only have one default saved cart.')
            ),
            # Ensure cart data is not empty
            models.CheckConstraint(
                check=models.Q(cart_data__gt={}),
                name='saved_cart_data_not_empty',
                violation_error_message=_('Cart data cannot be empty.')
            ),
            # Ensure name is provided if not default
            models.CheckConstraint(
                check=models.Q(is_default=True) | ~models.Q(name=''),
                name='saved_cart_name_required',
                violation_error_message=_('Name is required for non-default saved carts.')
            )
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

    def is_valid(self) -> bool:
        """
        Check if the saved cart is valid.

        Returns:
            bool: True if the saved cart is valid, False otherwise
        """
        if not super().is_valid():
            logger.warning(f"SavedCart {self.pk} validation failed: Parent validation failed")
            return False

        # Check required fields
        required_fields = {
            'user': self.user_id,
            'cart_data': self.cart_data,
        }

        for field, value in required_fields.items():
            if not value:
                logger.warning(f"SavedCart {self.pk} validation failed: Missing required field {field}")
                return False

        # Validate cart_data structure
        if not isinstance(self.cart_data, dict):
            logger.warning(f"SavedCart {self.pk} validation failed: cart_data must be a dictionary")
            return False

        # If this is not the default cart, name is required
        if not self.is_default and not self.name:
            logger.warning(f"SavedCart {self.pk} validation failed: Name is required for non-default saved carts")
            return False

        # Validate items in cart_data
        if 'items' in self.cart_data:
            if not isinstance(self.cart_data['items'], list):
                logger.warning(f"SavedCart {self.pk} validation failed: cart_data.items must be a list")
                return False

            # Validate each item in the cart
            for item in self.cart_data.get('items', []):
                if not all(key in item for key in ['product_id', 'quantity']):
                    logger.warning(f"SavedCart {self.pk} validation failed: Invalid item format in cart_data")
                    return False

                try:
                    quantity = int(item['quantity'])
                    if quantity <= 0:
                        logger.warning(f"SavedCart {self.pk} validation failed: Invalid quantity in cart item")
                        return False
                except (ValueError, TypeError):
                    logger.warning(f"SavedCart {self.pk} validation failed: Invalid quantity type in cart item")
                    return False

        logger.debug(f"SavedCart {self.pk} validation successful")
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the saved cart can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
                - can_delete: True if the cart can be deleted, False otherwise
                - reason: Empty string if can_delete is True, otherwise the reason why it can't be deleted
        """
        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        # Check if this is the default cart
        if self.is_default:
            return False, "Cannot delete the default saved cart. Set another cart as default first."

        # Check if this cart is being used in any active orders
        if hasattr(self, 'orders') and self.orders.filter(is_deleted=False).exists():
            return False, "Cannot delete a saved cart that is associated with orders"

        return True, ""

    def clean(self):
        """Run model validation before saving."""
        super().clean()

        # Normalize name
        if self.name:
            self.name = self.name.strip()

        # Set default name if not provided and not default cart
        if not self.name and not self.is_default:
            self.name = f"Saved Cart {timezone.now().strftime('%Y-%m-%d %H:%M')}"

    def save(self, *args, **kwargs):
        """Override save to handle default cart logic."""
        # If this is being set as default, unset other defaults
        if self.is_default and hasattr(self, 'user'):
            self.user.saved_carts.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)

        # If this is the first cart, make it default
        if hasattr(self, 'user') and not self.user.saved_carts.exists():
            self.is_default = True

        super().save(*args, **kwargs)
        logger.info(f"SavedCart {self.pk} saved for user {self.user_id}")

    @property
    def item_count(self) -> int:
        """Return the total number of items in the cart."""
        if not isinstance(self.cart_data, dict) or 'items' not in self.cart_data:
            return 0
        return len(self.cart_data['items'])

    @property
    def total_quantity(self) -> int:
        """Return the total quantity of all items in the cart."""
        if not isinstance(self.cart_data, dict) or 'items' not in self.cart_data:
            return 0
        return sum(item.get('quantity', 0) for item in self.cart_data['items'])

    def restore_to_cart(self, user):
        """Restore this saved cart to an active cart for the user."""

        # Get or create user's active cart
        cart, created = Cart.objects.get_or_create(
            user=user,
            is_active=True,
            is_deleted=False
        )

        # Clear existing cart items
        cart.cart_items.all().delete()

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