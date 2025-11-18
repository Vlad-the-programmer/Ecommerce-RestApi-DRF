import logging
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from decimal import Decimal, DecimalException

from common.models import CommonModel
from reviews.managers import ReviewManager
from reviews.utils import get_stars_for_rating

logger = logging.getLogger(__name__)


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

        Args:
            log_errors: If True, logs validation errors to the logger.

        Returns:
            bool: True if the review is valid, False otherwise
        """
        validation_errors = []

        # Call parent's is_valid first
        if not super().is_valid():
            validation_errors.append("Base validation failed (inactive or deleted)")

        # Check required fields
        if not self.user_id:
            validation_errors.append("User is required")
        if not self.product_id:
            validation_errors.append("Product is required")
        if self.rating is None:
            validation_errors.append("Rating is required")

        # Rating validation
        try:
            rating = Decimal(str(self.rating)) if not isinstance(self.rating, Decimal) else self.rating
            if not (Decimal('0.00') <= rating <= Decimal('5.00')):
                validation_errors.append(f"Rating must be between 0.00 and 5.00, got {rating}")
        except (ValueError, DecimalException, TypeError) as e:
            validation_errors.append(f"Invalid rating value: {self.rating} ({str(e)})")

        # Content validation
        if self.content and not self.content.strip():
            validation_errors.append("Content cannot be empty if provided")

        # Title validation
        if self.title and len(self.title) > 255:
            validation_errors.append(f"Title cannot exceed 255 characters (got {len(self.title)})")

        # User validation
        if hasattr(self, 'user') and (not self.user or not self.user.is_active):
            validation_errors.append("User is inactive or does not exist")

        # Product validation
        if hasattr(self, 'product'):
            if not self.product:
                validation_errors.append("Product does not exist")
            elif self.product.is_deleted:
                validation_errors.append("Cannot review a deleted product")

        # Log validation errors if any
        if validation_errors:
            logger.warning(
                f"Review validation failed for {self} - User: {getattr(self, 'user_id', 'None')}, "
                f"Product: {getattr(self, 'product_id', 'None')}. "
                f"Errors: {', '.join(validation_errors)}"
            )

        return not bool(validation_errors)

    def clean(self):
        """
        Validate model fields before saving.
        Raises ValidationError if any validation fails.
        """
        super().clean()
        
        # Convert rating to Decimal if it's not already
        try:
            if self.rating is not None:
                self.rating = Decimal(str(self.rating)).quantize(Decimal('0.01'))
        except (ValueError, DecimalException) as e:
            raise ValidationError({
                'rating': _("Rating must be a valid number.")
            }) from e
            
        # Validate rating range
        if self.rating is not None and (self.rating < 0 or self.rating > 5):
            raise ValidationError({
                'rating': _("Rating must be between 0.00 and 5.00.")
            })
            
        # Validate content length if provided
        if self.content and len(self.content.strip()) == 0:
            raise ValidationError({
                'content': _("Content cannot be empty if provided.")
            })
            
        # Validate title length if provided
        if self.title and len(self.title.strip()) > 255:
            raise ValidationError({
                'title': _("Title cannot exceed 255 characters.")
            })

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the review can be safely soft-deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        # Check base class can_be_deleted first
        base_can_delete, reason = super().can_be_deleted()
        if not base_can_delete:
            return False, reason

        # Check if review is already deleted
        if self.is_deleted:
            return False, "Review is already deleted"

        # Additional business rules can be added here
        # For example, prevent deletion of reviews that are too old
        max_days_to_delete = 30  # Example: Allow deletion within 30 days
        if (timezone.now() - self.date_created).days > max_days_to_delete:
            return False, f"Cannot delete reviews older than {max_days_to_delete} days"

        return True, ""

    def short_content(self):
        """Shortened preview for admin or listings."""
        if not self.content:
            return ""
        content = self.content.strip()
        return (content[:75] + "...") if len(content) > 75 else content

    def rating_in_stars(self) -> str:
        """
        Returns a string of stars based on the rating.
        
        Returns:
            str: A string representation of the rating in stars
        """
        if self.rating is None:
            return "No rating"
        try:
            rating = float(self.rating)
            return get_stars_for_rating(rating)
        except (TypeError, ValueError) as e:
            logger.error(f"Error converting rating to stars for review {self.id}: {e}")
            return "Rating error"
