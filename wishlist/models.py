from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel, ItemCommonModel


class WishListItemPriority(models.IntegerChoices):
    LOW = 1, _("Low")
    MEDIUM = 2, _("Medium")
    HIGH = 3, _("High")


class Wishlist(CommonModel):
    """
    Represents a user's wishlist containing multiple products.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
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
        db_table = "wishlist"
        verbose_name = _("Wishlist")
        verbose_name_plural = _("Wishlists")
        constraints = [
            models.CheckConstraint(
                check=Q(is_deleted=False),
                name="wishlist_not_deleted_check"
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="wishlist_user_idx"),
            models.Index(fields=["is_public", "is_deleted"], name="wishlist_public_status_idx"),
        ]

    def __str__(self):
        return f"Wishlist: {self.user} - {self.name}"

    @property
    def items_count(self):
        """Return the number of items in this wishlist."""
        return self.wishlist_items.count()

    def clean(self):
        super().clean()
        # Ensure user doesn't have multiple wishlists
        if not self.pk and Wishlist.objects.filter(user=self.user, is_deleted=False).exists():
            raise ValidationError(
                {"user": _("User can only have one active wishlist.")}
            )


class WishListItem(ItemCommonModel):
    """
    Stores items users have added to their wishlist.
    """
    wishlist = models.ForeignKey(
        "wishlist.Wishlist",
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        verbose_name=_("Wishlist"),
        help_text=_("Wishlist to which this item belongs."),
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
            models.CheckConstraint(
                check=Q(is_deleted=False),
                name="wishlist_item_not_deleted_check"
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

    def clean(self):
        """
        Ensure logical consistency before saving.
        """
        super().clean()

        # Ensure wishlist belongs to the user
        if self.wishlist.user != self.user:
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
