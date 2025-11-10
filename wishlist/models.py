from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel, ItemCommonModel
from wishlist.managers import WishListManager, WishListItemManager


class WishListItemPriority(models.IntegerChoices):
    LOW = 1, _("Low")
    MEDIUM = 2, _("Medium")
    HIGH = 3, _("High")


class Wishlist(CommonModel):
    """
    Represents a user's wishlist containing multiple products.
    """
    objects = WishListManager()

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="wishlist",
        verbose_name=_("User"),
        help_text=_("User who owns this wishlist."),
    )

    name = models.CharField(
        max_length=100,
        default=_("My Wishlist"),
        verbose_name=_("Wishlist Name"),
        help_text=_("Name for this wishlist."),
    )

    is_public = models.BooleanField(
        default=False,
        verbose_name=_("Is Public"),
        help_text=_("Whether this wishlist is visible to other users."),
    )

    class Meta:
        db_table = "wishlists"
        verbose_name = _("Wishlist")
        verbose_name_plural = _("Wishlists")
        constraints = [
            models.CheckConstraint(
                check=Q(is_deleted=False),
                name="wishlist_not_deleted_check"
            ),
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(is_deleted=False),
                name='unique_active_wishlist_per_user'
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="wishlist_user_idx"),
            models.Index(fields=["is_public", "is_deleted"], name="wishlist_public_status_idx"),
            models.Index(fields=["user", "is_public", "is_deleted"], name="wishlist_user_is_public_idx"),
        ]

    def __str__(self):
        return f"Wishlist: {self.user} - {self.name}"

    @property
    def items_count(self):
        """Return the number of items in this wishlist."""
        return self.wishlist_items.count()

    def clean(self):
        super().clean()
        # Ensure user doesn't have multiple active wishlists
        if not self.pk and Wishlist.objects.filter(
                user=self.user,
                is_deleted=False
        ).exists():
            raise ValidationError(
                {"user": _("User can only have one active wishlist.")}
            )

    def add_item(self, product, variant=None, quantity=1, note="", priority=WishListItemPriority.MEDIUM):
        """Add item to wishlist with validation."""
        # Check if item already exists
        existing_item = WishListItem.objects.filter(
            wishlist=self,
            product=product,
            variant=variant,
        ).first()

        if existing_item:
            # Update existing item
            existing_item.quantity = quantity
            existing_item.note = note
            existing_item.priority = priority
            existing_item.save()
            return existing_item, False
        else:
            # Create new item
            item = WishListItem.objects.create(
                wishlist=self,
                product=product,
                variant=variant,
                quantity=quantity,
                note=note,
                priority=priority,
                user=self.user  # Auto-set user
            )
            return item, True

    def remove_item(self, product, variant=None):
        """Remove item from wishlist using soft delete."""
        try:
            item = self.wishlist_items.get(
                product=product,
                variant=variant,
                is_deleted=False
            )
            item.delete()  # Soft delete
            return True
        except WishListItem.DoesNotExist:
            return False

    def clear(self):
        """Remove all items from wishlist."""
        self.wishlist_items.all().delete()

    def get_available_items(self):
        """Get all available items in wishlist."""
        return self.wishlist_items.filter(
            is_deleted=False
        )

    def get_items_by_priority(self):
        """Get items ordered by priority."""
        return self.wishlist_items.filter(
            is_deleted=False
        ).by_priority()

    def move_all_to_cart(self, cart):
        """Move all wishlist items to cart."""
        items = self.wishlist_items.filter(is_deleted=False)
        cart_items = []

        for item in items:
            cart_item = item.move_to_cart(cart)
            cart_items.append(cart_item)

        return cart_items


class WishListItem(ItemCommonModel):
    """
    Stores items users have added to their wishlist.
    """
    objects = WishListItemManager()

    wishlist = models.ForeignKey(
        "wishlist.Wishlist",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="wishlist_items",
        verbose_name=_("Wishlist"),
        help_text=_("Wishlist to which this item belongs."),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="wishlist_items"
    )

    note = models.TextField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("Note"),
        help_text=_("Optional note or comment for this wishlist item."),
    )

    priority = models.PositiveSmallIntegerField(
        default=1,
        choices=WishListItemPriority.choices,
        verbose_name=_("Priority"),
        help_text=_("How important this item is to the user."),
    )

    class Meta:
        db_table = "wishlist_item"
        verbose_name = _("Wishlist Item")
        verbose_name_plural = _("Wishlist Items")
        constraints = [
            models.UniqueConstraint(
                fields=["wishlist", "product", "variant"],
                name="unique_wishlist_product_variant",
                condition=Q(is_deleted=False)
            ),
            models.CheckConstraint(
                check=Q(quantity__gte=1),
                name="wishlist_item_quantity_min_1"
            ),
        ]
        indexes = [
            # Foreign key lookups
            models.Index(fields=["wishlist"], name="wl_item_wl_idx"),
            models.Index(fields=["product"], name="wl_item_product_idx"),
            models.Index(fields=["variant"], name="wl_item_variant_idx"),

            # Composite indexes for common queries
            models.Index(fields=["wishlist", "is_deleted"], name="wl_item_status_idx"),
            models.Index(fields=["priority", "date_created"], name="wl_item_priority_date_idx"),
        ]

    def __str__(self):
        variant_info = f" ({self.variant})" if self.variant else ""
        return f"Wishlist Item: {self.wishlist.user} - {self.product}{variant_info}"

    def save(self, *args, **kwargs):
        """Auto-set user from wishlist for soft delete consistency"""
        if self.wishlist and not self.user:
            self.user = self.wishlist.user
        super().save(*args, **kwargs)

    def clean(self):
        """
        Ensure logical consistency before saving.
        """
        super().clean()

        # Auto-set user from wishlist if not set
        if self.wishlist and not self.user:
            self.user = self.wishlist.user

        # Ensure wishlist belongs to the user (if both are set)
        if self.wishlist and self.user and self.wishlist.user != self.user:
            raise ValidationError(
                {"wishlist": _("Wishlist must belong to the user.")}
            )

        # Can't add deleted or inactive products
        if self.product and (self.product.is_deleted or not self.product.is_active):
            raise ValidationError(
                {"product": _("Cannot add inactive or deleted product to wishlist.")}
            )

        # Can't add deleted variant
        if self.variant and (self.variant.is_deleted or not self.variant.is_active):
            raise ValidationError(
                {"variant": _("Cannot add inactive or deleted variant to wishlist.")}
            )

        # Validate priority range
        if self.priority < 1 or self.priority > 5:  # Assuming 1-5 scale
            raise ValidationError(
                {"priority": _("Priority must be between 1 and 5.")}
            )

    def move_to_cart(self, cart):
        """Move this wishlist item to shopping cart."""
        from cart.models import CartItem

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=self.product,
            variant=self.variant,
            defaults={
                'quantity': self.quantity,
                'user': self.user
            }
        )

        if not created:
            cart_item.quantity += self.quantity
            cart_item.save()

        # Remove from wishlist after moving to cart
        self.delete()

        return cart_item


