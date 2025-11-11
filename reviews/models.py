from django.core.exceptions import ValidationError

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from common.models import CommonModel
from reviews.managers import ReviewManager
from reviews.utils import get_stars_for_rating


class Review(CommonModel):
    """User review for a product."""
    objects = ReviewManager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reviews",
        verbose_name=_("User"),
        help_text=_("The user who wrote the review."),
    )

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="reviews",
        verbose_name=_("Product"),
        help_text=_("The product this review refers to."),
    )

    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Product rating (0.00–5.00)."),
    )

    title = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Optional title for the review."),
    )

    content = models.TextField(
        blank=True,
        help_text=_("Detailed review text."),
    )

    class Meta:
        db_table = "product_reviews"
        verbose_name = _("Review")
        verbose_name_plural = _("Reviews")
        ordering = ["-date_created", "-rating"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=["product", "rating"], name="review_product_rating_idx"),
            models.Index(fields=["user", "product"], name="review_user_product_idx"),
            models.Index(fields=["is_deleted", "rating"], name="review_deleted_rating_idx"),
        ]
        constraints = [
            # Ensure rating is within allowed bounds
            models.CheckConstraint(
                check=models.Q(rating__gte=Decimal("0.00")) & models.Q(rating__lte=Decimal("5.00")),
                name="review_rating_range",
            ),
            # One active review per user per product
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_active_review_per_user_product",
                condition=models.Q(is_deleted=False),
            ),
        ]

    def __str__(self):
        return f"Review by {self.user} for {self.product} ({self.rating}/5)"

    def is_valid(self) -> bool:
        """
        Check if the review is valid according to business rules.

        Returns:
            bool: True if the review is valid, False otherwise
        """
        # Call parent's is_valid first
        if not super().is_valid():
            return False

        # Check required fields
        if not all([self.user_id, self.product_id, self.rating is not None]):
            return False

        # Rating must be between 0 and 5
        if not (Decimal('0.00') <= self.rating <= Decimal('5.00')):
            return False

        # If content is provided, it must be non-empty
        if self.content and not self.content.strip():
            return False

        # Title, if provided, should not exceed max length
        if self.title and len(self.title) > 255:
            return False

        # Check if user exists and is active
        if hasattr(self, 'user') and (not self.user or not self.user.is_active):
            return False

        # Check if product exists and is not deleted
        if hasattr(self, 'product') and (not self.product or self.product.is_deleted):
            return False

        return True

    def clean(self):
        """Ensure rating value is valid."""
        if self.rating < 0 or self.rating > 5:
            raise ValidationError(_("Rating must be between 0 and 5."))

    def short_content(self):
        """Shortened preview for admin or listings."""
        return (self.content[:75] + "...") if len(self.content) > 75 else self.content

    def rating_in_stars(self) -> str:
        """Returns a string of stars based on the rating."""
        rating = float(self.rating)  # Convert Decimal to float for easier comparison
        return get_stars_for_rating(rating)
