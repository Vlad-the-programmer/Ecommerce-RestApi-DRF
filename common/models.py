import logging
import uuid

from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ObjectDoesNotExist

from django_countries.fields import CountryField
from phonenumber_field.modelfields import PhoneNumberField
from rest_framework.exceptions import ValidationError


from cart.managers import CartItemManager
from common.managers import SoftDeleteManager
from orders.enums import OrderStatuses

logger = logging.getLogger(__name__)


class CommonModel(models.Model):
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, db_index=True)
    date_updated = models.DateTimeField(auto_now=True, null=True)
    date_deleted = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(verbose_name=_('Active'), default=True, db_index=True)
    is_deleted = models.BooleanField(verbose_name=_('Deleted'), default=False, db_index=True)

    class Meta:
        abstract = True
        indexes = [
            # Core manager patterns (used in ALL queries)
            models.Index(fields=['is_deleted']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_deleted', 'is_active']),

            # Date-based queries (common for reporting and cleanup)
            models.Index(fields=['date_created', 'is_deleted']),
            models.Index(fields=['is_deleted', 'date_deleted']),

            # Combined date and status queries
            models.Index(fields=['date_created', 'is_active', 'is_deleted']),

        ]
        constraints = [
            models.CheckConstraint(
                name="%(app_label)s_%(class)s_deleted_consistency",
                check=(
                        models.Q(is_deleted=True, date_deleted__isnull=False) |
                        models.Q(is_deleted=False, date_deleted__isnull=True)
                )
            )
        ]

    def is_valid(self, *args, **kwargs) -> bool:
        """Check if item is valid.

        Returns:
            bool: True if the item is active and not deleted, False otherwise
        """
        return self.is_active and not self.is_deleted

    def save(self, *args, **kwargs):
        """
              Save the model instance with validation and transaction support.

              Args:
                  *args: Variable length argument list.
                  **kwargs: Arbitrary keyword arguments.

              Raises:
                  ValidationError: If model validation fails.
                  Exception: For any other unexpected errors during save.
              """
        try:
            # Validate before saving
            self.full_clean()

            # Use a transaction to ensure atomicity
            with transaction.atomic():
                super().save(*args, **kwargs)

            logger.info(
                f"Successfully saved {self._meta.verbose_name} {self.pk}",
                extra={'model': self._meta.label, 'pk': self.pk}
            )

        except ValidationError as ve:
            logger.error(
                f"Validation error saving {self._meta.verbose_name} {getattr(self, 'pk', 'NEW')}: {str(ve)}",
                exc_info=True,
                extra={'model': self._meta.label, 'pk': getattr(self, 'pk', None)}
            )
            raise
        except Exception as e:
            logger.critical(
                f"Unexpected error saving {self._meta.verbose_name} {getattr(self, 'pk', 'NEW')}: {str(e)}",
                exc_info=True,
                extra={'model': self._meta.label, 'pk': getattr(self, 'pk', None)}
            )
            raise

    def clean(self):
        """Run model validation before saving."""
        if not self.is_valid():
            logger.error(f"Cannot save invalid {self._meta.verbose_name}: {self}")
            raise ValidationError(_(f"Cannot save invalid {self._meta.verbose_name}"))
        super().clean()

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if item can be safely soft-deleted.
        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        if self.is_deleted:
            return False, f"{self.__class__.__name__.title()} is already deleted"

        return True, ""

    def _check_can_be_deleted_or_raise_error(self):
        # Check if can be deleted
        can_delete, reason = self.can_be_deleted()
        if not can_delete:
            logger.warning(f"Cannot delete {self._meta.verbose_name} {self.id}: {reason}")
            raise ValidationError(_(f"Cannot delete {self._meta.verbose_name}: {reason}"))
        logger.warning(f"{self._meta.verbose_name} {self.id} can be safely deleted")

    def delete(self, *args, **kwargs):
        """
        Soft delete: mark as deleted and update related objects.
        Uses transaction to ensure all operations complete successfully or none do.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
                - update_fields (bool): If True, updates fields directly via save().
                                       If False, uses direct SQL update. Defaults to True.

        Returns:
            bool: True if deletion was successful.

        Raises:
            ValidationError: If the instance cannot be deleted due to protected relations.
            Exception: For any other unexpected errors during deletion.
        """
        try:
            with transaction.atomic():
                # Check if the instance can be deleted
                self._check_can_be_deleted_or_raise_error()

                # Update instance fields
                self.is_deleted = True
                self.is_active = False
                self.date_deleted = timezone.now()

                # Save with or without signals based on kwargs
                update_fields = ["is_deleted", "is_active", "date_deleted", "date_updated"]
                if kwargs.pop('update_fields', True):
                    self.save(update_fields=update_fields)
                else:
                    # Direct SQL update to avoid signal recursion
                    self.__class__._default_manager.filter(pk=self.pk).update(
                        is_deleted=True,
                        is_active=False,
                        date_deleted=timezone.now(),
                        date_updated=timezone.now()
                    )
                    # Refresh instance to reflect changes
                    self.refresh_from_db(fields=update_fields)

                # Handle related objects
                self._handle_related_objects_on_delete()

                logger.info(
                    f"Successfully soft-deleted {self._meta.verbose_name} {self.pk}",
                    extra={'model': self._meta.label, 'pk': self.pk}
                )
                return True

        except ValidationError as ve:
            logger.error(
                f"Validation error deleting {self._meta.verbose_name} {self.pk}: {str(ve)}",
                exc_info=True,
                extra={'model': self._meta.label, 'pk': self.pk}
            )
            raise
        except Exception as e:
            logger.critical(
                f"Unexpected error deleting {self._meta.verbose_name} {self.pk}: {str(e)}",
                exc_info=True,
                extra={'model': self._meta.label, 'pk': self.pk}
            )
            raise

    def _handle_related_objects_on_delete(self):
        """Handle related objects when the instance is deleted."""
        for rel in self._meta.related_objects:
            related_manager = getattr(self, rel.get_accessor_name(), None)
            if not related_manager:
                continue

            if rel.on_delete == models.PROTECT:
                if related_manager.exists():
                    raise ValidationError(
                        f"Cannot delete {self._meta.verbose_name} because it is referenced by {rel.related_model._meta.verbose_name}"
                    )
            elif rel.on_delete == models.SET_NULL:
                if hasattr(related_manager, 'all'):
                    # For many-to-many or reverse foreign key
                    related_manager.update(**{rel.field.name: None})
                else:
                    # For one-to-one or foreign key
                    setattr(self, rel.get_accessor_name(), None)
                    self.save(update_fields=[rel.get_accessor_name().split('_')[0]])

    def hard_delete(self, *args, **kwargs):
        """Permanently delete the instance from the database."""
        try:
            with transaction.atomic():
                super().delete(*args, **kwargs)
                logger.info(
                    f"Successfully hard-deleted {self._meta.verbose_name} {self.pk}",
                    extra={'model': self._meta.label, 'pk': self.pk}
                )
        except Exception as e:
            logger.error(
                f"Error hard-deleting {self._meta.verbose_name} {self.pk}: {str(e)}",
                exc_info=True,
                extra={'model': self._meta.label, 'pk': self.pk}
            )
            raise

    def restore(self):
        """Restore a soft-deleted instance."""
        if not self.is_deleted:
            return False

        try:
            with transaction.atomic():
                self.is_deleted = False
                self.is_active = True
                self.date_deleted = None
                self.save(update_fields=["is_deleted", "is_active", "date_deleted", "date_updated"])
                logger.info(
                    f"Successfully restored {self._meta.verbose_name} {self.pk}",
                    extra={'model': self._meta.label, 'pk': self.pk}
                )
                return True
        except Exception as e:
            logger.error(
                f"Error restoring {self._meta.verbose_name} {self.pk}: {str(e)}",
                exc_info=True,
                extra={'model': self._meta.label, 'pk': self.pk}
            )
            raise


class AuthCommonModel(CommonModel):
    """CommonModel without date_created for user auth model that have date_joined."""

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['is_deleted']),
            models.Index(fields=['is_deleted', 'is_active']),
            models.Index(fields=['is_deleted', 'date_deleted']),
        ]

    date_created = None


class AddressBaseModel(CommonModel):
    # AddressBaseModel line approach (common for e-commerce)
    address_line_1 = models.CharField(max_length=255,
                                      help_text=_("Street address, P.O. box, company name"), db_index=True)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True,
                                      help_text=_("Apartment, suite, unit, building, floor, etc."))
    # Optional detailed breakdown
    house_number = models.CharField(max_length=20, blank=True, null=True)
    street = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    apartment_number = models.CharField(max_length=50, blank=True, null=True)
    zip_code = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    city = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    state = models.CharField(max_length=50, null=True, blank=True, db_index=True,
                             help_text=_("State/Province/Region (e.g., Massachusetts, Ontario, Bavaria)"))
    country = CountryField(null=True, blank=True, db_index=True)

    def __str__(self):
        return f"{self.address_line_1}, {self.city}, {self.state}, {self.country}"

    class Meta:
        abstract=True
        ordering = ["-is_active", "-date_created"]
        indexes = CommonModel.Meta.indexes + [

            # Location-based indexes
            models.Index(fields=["country", "is_deleted"]),  # Regional analytics
            models.Index(fields=["city", "is_deleted"]),  # City-based queries
            models.Index(fields=["state", "is_deleted"]),  # State-based queries
            models.Index(fields=["zip_code", "is_deleted"]),  # Zip code lookups

            # Composite location indexes
            models.Index(fields=["country", "state", "city", "is_deleted"]),  # Full location queries

        ]
        constraints = [
            # Ensure at least one of street or address_line_1 is provided
            models.CheckConstraint(
                check=(
                        models.Q(street__isnull=False) |
                        models.Q(address_line_1__isnull=False)
                ),
                name='%(app_label)s_%(class)s_require_street_or_address_line',
                violation_error_message=_('Either street or address line 1 is required.')
            ),
            # Ensure city is provided
            models.CheckConstraint(
                check=models.Q(city__isnull=False) & ~models.Q(city=''),
                name='%(app_label)s_%(class)s_require_city',
                violation_error_message=_('City is required.')
            ),
            # Ensure country is provided
            models.CheckConstraint(
                check=models.Q(country__isnull=False) & ~models.Q(country=''),
                name='%(app_label)s_%(class)s_require_country',
                violation_error_message=_('Country is required.')
            ),
            # Ensure zip_code is valid if provided
            models.CheckConstraint(
                check=(
                        models.Q(zip_code__isnull=True) |
                        (models.Q(zip_code__isnull=False) & ~models.Q(zip_code=''))
                ),
                name='%(app_label)s_%(class)s_valid_zip_code',
                violation_error_message=_('ZIP code must be non-empty if provided.')
            )
        ]

    @property
    def full_address(self):
        """Get formatted address string"""
        components = [
            self.address_line_1,
            self.address_line_2,
            f"{self.city}, {self.state} {self.zip_code}" if self.city and self.state else None,
            self.country.name if self.country else None
        ]
        return ", ".join(filter(None, components))

    def is_valid(self, *args, **kwargs) -> bool:
        """
        Check if the address is valid according to business rules.

        Validates:
        1. Parent class validation (is_active, is_deleted, etc.)
        2. Either street or address_line_1 is provided
        3. City is provided and not empty
        4. Country is provided and not empty
        5. ZIP code is valid if provided
        6. State is valid if provided

        Returns:
            bool: True if the address is valid, False otherwise
        """
        # Check parent class validation
        if not super().is_valid():
            logger.warning(f"{self.__class__.__name__} validation failed: Parent class validation failed")
            return False

        # Check required fields
        required_fields = {
            'city': self.city,
            'country': self.country
        }

        for field, value in required_fields.items():
            if not value:
                logger.warning(f"{self.__class__.__name__} validation failed: Missing required field {field}")
                return False

        # Check at least one of street or address_line_1 is provided
        if not (self.street or self.address_line_1):
            logger.warning(f"{self.__class__.__name__} validation failed: Either street or address_line_1 is required")
            return False

        # Check zip_code is not empty if provided
        if self.zip_code is not None and not self.zip_code.strip():
            logger.warning(f"{self.__class__.__name__} validation failed: ZIP code cannot be empty if provided")
            return False

        # Check state is valid if country requires it
        if hasattr(self, 'country') and self.country and not self._is_valid_state():
            logger.warning(f"{self.__class__.__name__} validation failed: Invalid state for country {self.country}")
            return False

        return True

    def _is_valid_state(self) -> bool:
        """
        Check if the state is valid for the selected country.

        Returns:
            bool: True if state is valid or not required, False otherwise
        """
        # Skip validation if state is not required or not provided
        if not self.state or not self.country:
            return True

        # Add country-specific state validation here if needed
        # Example:
        # if self.country == 'US' and self.state not in US_STATES:
        #     return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the address can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
                - can_delete: True if the address can be deleted, False otherwise
                - reason: Empty string if can_delete is True, otherwise the reason why it can't be deleted
        """
        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        # Check if address is used in any orders
        if hasattr(self, 'orders') and self.orders.exists():
            return False, "Cannot delete address that is used in orders"

        # Check if address is a default shipping/billing address
        if hasattr(self, 'is_default') and self.is_default:
            return False, "Cannot delete default address. Set another address as default first."

        return True, ""

    def clean(self):
        """Run model validation before saving."""
        super().clean()

        # Normalize fields
        if self.city:
            self.city = self.city.strip()
        if self.state:
            self.state = self.state.strip()
        if self.zip_code:
            self.zip_code = self.zip_code.strip()


class ItemCommonModel(CommonModel):
    """Item model base for models like CartItem, OrderItem etc. Represents a product"""

    objects = CartItemManager()

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Product for this item")
    )
    quantity = models.PositiveIntegerField(
        help_text=_("Quantity of the product"),
        default=1
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text=_("Total price of the product")
    )

    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text=_("Selected variant for this cart item")
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['is_deleted', 'is_active', 'product']),
            models.Index(fields=['is_deleted', 'is_active', 'variant']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'variant'],
                name='unique_item',
                condition=models.Q(is_deleted=False)
            ),
            models.CheckConstraint(
                check=models.Q(product__isnull=False) | models.Q(variant__isnull=False),
                name='product_or_variant_must_be_set'
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=1),
                name='quantity_must_be_at_least_1'
            )
        ]

    def can_be_deleted(self):
        """Check if item can be safely soft-deleted."""
        if not super().can_be_deleted()[0]:
            return False, super().can_be_deleted()[1]

        # Check for active orders with this variant
        from orders.models import OrderItem
        from orders.enums import active_order_statuses
        if OrderItem.objects.filter(
                variant=self,
                order__status__in=active_order_statuses
        ).exists():
            return False, "Cannot delete variant with active or pending orders"

        product_can_be_deleted, reason = self.product.can_be_deleted()
        if not product_can_be_deleted:
            return False, reason

    @property
    def is_available(self):
        """
        Comprehensive availability check considering:
        - Item's own active/deleted status
        - Product/variant existence and status
        - Stock availability
        - Soft deletion of related objects
        """
        # Check if the item itself is active and not deleted
        if not self.is_active or self.is_deleted:
            return False

        try:
            if self.variant_id:
                # Check variant availability
                if not hasattr(self, '_variant_cache'):
                    from products.models import ProductVariant
                    try:
                        self._variant_cache = ProductVariant.objects.get(
                            pk=self.variant_id,
                            is_deleted=False,
                            is_active=True
                        )
                    except ProductVariant.DoesNotExist:
                        return False

                variant = self._variant_cache
                return (
                        variant.is_active and
                        not variant.is_deleted and
                        variant.is_in_stock and
                        variant.quantity_available >= self.quantity
                )

            elif self.product_id:
                # Check product availability
                if not hasattr(self, '_product_cache'):
                    from products.models import Product
                    try:
                        self._product_cache = Product.objects.get(
                            pk=self.product_id,
                            is_deleted=False,
                            is_active=True
                        )
                    except Product.DoesNotExist:
                        return False

                product = self._product_cache
                from products.enums import ProductStatus, StockStatus
                return (
                        product.is_active and
                        not product.is_deleted and
                        product.status == ProductStatus.PUBLISHED and
                        product.stock_status == StockStatus.IN_STOCK and
                        product.stock_quantity >= self.quantity
                )

            return False

        except (ObjectDoesNotExist, AttributeError):
            # Handle cases where related objects don't exist or can't be accessed
            return False

    @property
    def availability_status(self):
        """
        Detailed availability status with reasons.
        Useful for showing why an item is unavailable.
        """
        if not self.is_active or self.is_deleted:
            return "item_inactive", _("This item is no longer active")

        if not self.product_id and not self.variant_id:
            return "missing_product", _("Product information is missing")

        try:
            if self.variant_id:
                from products.models import ProductVariant
                try:
                    variant = ProductVariant.objects.get(pk=self.variant_id)
                    if variant.is_deleted:
                        return "variant_deleted", _("This variant has been removed")
                    if not variant.is_active:
                        return "variant_inactive", _("This variant is not active")
                    if not variant.is_in_stock:
                        return "out_of_stock", _("This variant is out of stock")
                    if variant.quantity_available < self.quantity:
                        return "insufficient_stock", _("Not enough stock available")
                    return "available", _("Available")
                except ProductVariant.DoesNotExist:
                    return "variant_not_found", _("Variant not found")

            elif self.product_id:
                from products.models import Product
                try:
                    product = Product.objects.get(pk=self.product_id)
                    if product.is_deleted:
                        return "product_deleted", _("This product has been removed")
                    if not product.is_active:
                        return "product_inactive", _("This product is not active")

                    from products.enums import ProductStatus, StockStatus
                    if product.status != ProductStatus.PUBLISHED:
                        return "product_unavailable", _("This product is not available")
                    if product.stock_status != StockStatus.IN_STOCK:
                        return "out_of_stock", _("This product is out of stock")
                    if product.stock_quantity < self.quantity:
                        return "insufficient_stock", _("Not enough stock available")
                    return "available", _("Available")
                except Product.DoesNotExist:
                    return "product_not_found", _("Product not found")

        except Exception:
            return "error", _("Unable to check availability")

        return "unknown", _("Availability unknown")

    @property
    def can_be_purchased(self):
        """
        Simplified check for purchase eligibility.
        Includes business logic rules beyond basic availability.
        """
        if not self.is_available:
            return False

        # Additional business rules can be added here
        # Example: Check for age restrictions, geographic restrictions, etc.

        return True

    @property
    def item_final_price(self) -> Decimal:
        """Final price for this item, taking variant into account with proper error handling"""
        try:
            if self.variant and hasattr(self.variant, 'final_price'):
                return Decimal(str(self.variant.final_price))

            if self.product and hasattr(self.product, 'get_price_for_variant'):
                price = self.product.get_price_for_variant(
                    color=getattr(self.variant, 'color', None),
                    size=getattr(self.variant, 'size', None)
                )
                return Decimal(str(price)) if price else Decimal('0.0')

            # Fallback to stored price or zero
            return self.total_price / Decimal(str(self.quantity)) if self.quantity > 0 else Decimal('0.0')

        except (AttributeError, ValueError, ZeroDivisionError):
            return Decimal('0.0')

    def get_availability_info(self):
        """
        Return comprehensive availability information.
        Useful for API responses or detailed error messages.
        """
        status, message = self.availability_status

        info = {
            'is_available': self.is_available,
            'status': status,
            'message': message,
            'can_purchase': self.can_be_purchased,
            'requested_quantity': self.quantity,
            'available_quantity': self.get_available_quantity()
        }

        # Add product/variant specific info
        if self.variant_id and hasattr(self, '_variant_cache'):
            info.update({
                'variant_stock': self._variant_cache.quantity_available,
                'variant_is_active': self._variant_cache.is_active,
            })
        elif self.product_id and hasattr(self, '_product_cache'):
            info.update({
                'product_stock': self._product_cache.stock_quantity,
                'product_status': self._product_cache.status,
            })

        return info

    def get_available_quantity(self):
        """Get maximum quantity that can be ordered"""
        try:
            if self.variant_id:
                if not hasattr(self, '_variant_cache'):
                    from products.models import ProductVariant
                    self._variant_cache = ProductVariant.objects.get(pk=self.variant_id)
                return min(self.quantity, self._variant_cache.quantity_available)

            elif self.product_id:
                if not hasattr(self, '_product_cache'):
                    from products.models import Product
                    self._product_cache = Product.objects.get(pk=self.product_id)
                return min(self.quantity, self._product_cache.stock_quantity)

            return 0

        except (ObjectDoesNotExist, AttributeError):
            return 0

    def clean(self):
        """Validate item before saving"""
        super().clean()

        # Ensure at least one of product or variant is set
        if not self.product_id and not self.variant_id:
            raise ValidationError(_("Either product or variant must be set."))

        # Validate quantity is positive
        if self.quantity < 1:
            raise ValidationError(_("Quantity must be at least 1."))

        # Check availability if item is active
        if self.is_active and not self.is_deleted:
            if not self.is_available:
                raise ValidationError(
                    _("Cannot add unavailable item. %(reason)s") %
                    {'reason': self.availability_status[1]}
                )

    def save(self, *args, **kwargs):
        """Automatically calculate total price before saving with validation"""
        # Calculate price
        price = self.item_final_price
        quantity = Decimal(str(self.quantity))
        self.total_price = price * quantity

        super().save(*args, **kwargs)


class SlugFieldCommonModel(CommonModel):
    """Common model for models with slug field"""
    slug_fields = []  # List of fields to use for slug generation (must set in child model)

    slug = models.SlugField(
        unique=True,
        max_length=255,
        blank=True,
        verbose_name=_("URL Slug"),
        help_text=_("Unique URL-friendly identifier for the product")
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['slug'], name='common_slug_idx'),
        ]

    def check_slug_unique(self, slug: str) -> bool:
        queryset = self.__class__.objects.filter(slug=slug)
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)
        return not queryset.exists()

    def _get_field_value_without_joins(self, field: str):
        """
        Get field value without creating join queries.
        Handles direct fields and simple foreign key relationships.
        """
        # Handle direct fields
        if '__' not in field:
            return getattr(self, field, None)

        # Handle foreign key relationships without joins
        parts = field.split('__')
        current_obj = self

        for part in parts:
            if not current_obj:
                return None

            # Get the related object ID first
            field_obj = current_obj._meta.get_field(part)
            if isinstance(field_obj, models.ForeignKey):
                # Get the foreign key ID
                fk_id = getattr(current_obj, field_obj.attname)  # This gets the ID without join
                if not fk_id:
                    return None

                # Get the related object from database if needed
                try:
                    current_obj = field_obj.related_model.objects.get(pk=fk_id)
                except field_obj.related_model.DoesNotExist:
                    return None
            else:
                # For non-foreign key fields in the chain
                current_obj = getattr(current_obj, part, None)

        return str(current_obj) if current_obj else None

    def generate_unique_slug(self, fields_to_slugify: list[str]) -> Optional[str]:
        field_values = []
        for field in fields_to_slugify:
            # Use the safe method that avoids joins
            value = self._get_field_value_without_joins(field)
            if value:
                field_values.append(str(value))

        if not field_values:
            return None

        base_slug = slugify("-".join(field_values))
        slug = base_slug
        counter = 1

        while not self.check_slug_unique(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1
            if counter > 100:
                slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                break

        return slug

    def _generate_and_set_slug(self, fields_to_slugify_list: list[str]):
        generated_slug = self.generate_unique_slug(fields_to_slugify_list)
        if generated_slug:
            self.__class__.objects.filter(pk=self.pk).update(slug=generated_slug)
            self.slug = generated_slug
        else:
            fallback_slug = slugify(f"{self.__class__.__name__.lower()}-{self.uuid}")
            self.__class__.objects.filter(pk=self.pk).update(slug=fallback_slug)
            self.slug = fallback_slug

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new or not self.slug:
            # Customize fields used to generate slug per model
            fields_to_slugify = getattr(self, "slug_fields", ["slug"])
            self._generate_and_set_slug(fields_to_slugify)
        super().save(*args, **kwargs)


class ShippingAddress(AddressBaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="shipping_addresses")
    is_default = models.BooleanField(default=False, help_text=_("Set as default shipping address"))

    def __str__(self):
        parts = []
        if self.address_line_1:
            parts.append(self.address_line_1)
        if self.address_line_2:
            parts.append(self.address_line_2)
        parts.extend([self.city, self.state, self.zip_code, str(self.country)])
        return ', '.join(parts)

    class Meta:
        db_table = "shipping_addresses"
        verbose_name = "Shipping Address"
        verbose_name_plural = "Shipping Addresses"
        ordering = ["-is_default", "-date_created"]  # Default addresses first, then newest
        indexes = AddressBaseModel.Meta.indexes + [
            # Core relationship indexes
            models.Index(fields=["user", "is_deleted"]),  # User's addresses + manager
            models.Index(fields=["user", "is_default", "is_deleted"]),  # User's default address


            models.Index(fields=["user", "country", "is_deleted"]),  # User's addresses by country

            # Default address quick lookup
            models.Index(fields=["is_default", "is_deleted"]),  # All default addresses
        ]
        constraints = AddressBaseModel.Meta.constraints + [
            # Ensure phone number is valid if provided
            models.CheckConstraint(
                check=(
                        models.Q(phone__isnull=True) |
                        models.Q(phone__regex=r'^\+?[0-9\s-]{5,20}$')
                ),
                name='%(app_label)s_%(class)s_valid_phone',
                violation_error_message=_('Enter a valid phone number.')
            ),
            # Ensure at least one contact method is provided
            models.CheckConstraint(
                check=(
                        models.Q(phone__isnull=False) |
                        models.Q(email__isnull=False)
                ),
                name='%(app_label)s_%(class)s_require_contact',
                violation_error_message=_('At least one contact method (phone or email) is required.')
            ),
            # Prevent duplicate default addresses per user
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_default=True, is_deleted=False),
                name='%(app_label)s_%(class)s_single_default',
                violation_error_message=_('User can only have one default shipping address.')
            )
        ]

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the shipping address can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
                - can_delete: True if the address can be deleted, False otherwise
                - reason: Empty string if can_delete is True, otherwise the reason why it can't be deleted
        """
        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        # Check if this is the only shipping address
        if hasattr(self, 'user') and self.user.shipping_addresses.count() <= 1:
            return False, "Cannot delete the only shipping address"

        # Check if this is the default address and there are other addresses
        if self.is_default and hasattr(self, 'user'):
            other_addresses = self.user.shipping_addresses.exclude(pk=self.pk).exists()
            if not other_addresses:
                return False, "Cannot delete the only shipping address"
            if not self.user.shipping_addresses.filter(is_default=True).exclude(pk=self.pk).exists():
                return False, "Set another address as default before deleting this one"

        # Check if this address is used in any orders
        if hasattr(self, 'orders') and self.orders.exists():
            return False, "Cannot delete shipping address used in orders"

        # Check if this address is used in any shipments
        if hasattr(self, 'shipments') and self.shipments.exists():
            return False, "Cannot delete shipping address used in shipments"

        return True, ""

    def save(self, *args, **kwargs):
        """Override save to handle default address logic."""
        # If this is being set as default, unset other defaults
        if self.is_default and hasattr(self, 'user'):
            self.user.shipping_addresses.exclude(pk=self.pk).update(is_default=False)

        # If this is the first address, make it default
        if hasattr(self, 'user') and not self.user.shipping_addresses.exists():
            self.is_default = True

        super().save(*args, **kwargs)
        logger.info(f"ShippingAddress {self.pk} saved for user {getattr(self, 'user_id', 'unknown')}")


class BillingAddress(AddressBaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="billing_addresses")

    # Company information (for business purchases)
    company_name = models.CharField(max_length=100, blank=True, null=True,
                                    help_text=_("Company name (if applicable)"))
    tax_id = models.CharField(max_length=50, blank=True, null=True, help_text=_("VAT ID, GST number, etc."))

    # Contact person
    contact_name = models.CharField(max_length=100, help_text=_("Full name for billing contact"),
                                    null=True, blank=True)



    # Contact information
    email = models.EmailField(help_text=_("Email for billing receipts"), null=True, blank=True)
    phone = PhoneNumberField(blank=True, null=True)

    # Billing specific
    is_default = models.BooleanField(default=False, help_text=_("Set as default billing address"))
    is_business = models.BooleanField(default=False, help_text=_("Business address"))

    def __str__(self):
        parts = []
        if self.company_name:
            parts.append(self.company_name)
        parts.append(self.contact_name)
        if self.address_line_1:
            parts.append(self.address_line_1)
        if self.address_line_2:
            parts.append(self.address_line_2)
        parts.extend([self.city, self.state, self.zip_code, str(self.country)])
        return ', '.join(parts)

    class Meta:
        db_table = "billing_addresses"
        verbose_name = "Billing Address"
        verbose_name_plural = "Billing Addresses"
        ordering = ["-is_default", "-date_created"]
        indexes = AddressBaseModel.Meta.indexes + [
            # Core relationship indexes
            models.Index(fields=["user", "is_deleted"]),
            models.Index(fields=["user", "is_default", "is_deleted"]),
            models.Index(fields=["user", "is_business", "is_deleted"]),

            # Business-specific indexes
            models.Index(fields=["is_business", "is_deleted"]),
            models.Index(fields=["company_name", "is_deleted"]),

        ]
        constraints = AddressBaseModel.Meta.constraints + [
            # Ensure contact name is provided for non-business addresses
            models.CheckConstraint(
                check=(
                        models.Q(is_business=True) |
                        (models.Q(is_business=False) & models.Q(contact_name__isnull=False) & ~models.Q(
                            contact_name=''))
                ),
                name='%(app_label)s_%(class)s_require_contact_name',
                violation_error_message=_('Contact name is required for non-business addresses.')
            ),
            # Ensure email is provided and valid
            models.CheckConstraint(
                check=(
                        models.Q(email__isnull=False) &
                        ~models.Q(email='') &
                        models.Q(email__contains='@')
                ),
                name='%(app_label)s_%(class)s_valid_email',
                violation_error_message=_('A valid email address is required.')
            ),
            # Ensure tax_id is provided for business addresses
            models.CheckConstraint(
                check=(
                        ~models.Q(is_business=True) |
                        (models.Q(is_business=True) & models.Q(tax_id__isnull=False) & ~models.Q(tax_id=''))
                ),
                name='%(app_label)s_%(class)s_require_tax_id_for_business',
                violation_error_message=_('Tax ID is required for business addresses.')
            )
        ]

    def is_valid(self, *args, **kwargs) -> bool:
        """
        Check if the billing address is valid according to business rules.

        Validates:
        1. Parent class validation (address fields, etc.)
        2. Contact name is provided for non-business addresses
        3. Email is valid
        4. Tax ID is provided for business addresses
        5. Phone number is valid if provided

        Returns:
            bool: True if the billing address is valid, False otherwise
        """
        # Check parent class validation
        if not super().is_valid():
            logger.warning(f"BillingAddress validation failed: Parent class validation failed")
            return False

        # Check required fields
        required_fields = {
            'email': self.email,
            'contact_name': None if self.is_business else self.contact_name,
            'tax_id': self.tax_id if self.is_business else None
        }

        for field, value in required_fields.items():
            if value is not None and not value:
                logger.warning(f"BillingAddress validation failed: Missing required field {field}")
                return False

        # Validate email format
        if self.email and '@' not in self.email:
            logger.warning("BillingAddress validation failed: Invalid email format")
            return False

        # Validate phone number if provided
        if self.phone:
            try:
                parsed_phone = str(self.phone)
                if len(parsed_phone) < 5:  # Basic validation
                    logger.warning("BillingAddress validation failed: Invalid phone number")
                    return False
            except Exception as e:
                logger.warning(f"BillingAddress validation failed: {str(e)}")
                return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the billing address can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
                - can_delete: True if the address can be deleted, False otherwise
                - reason: Empty string if can_delete is True, otherwise the reason why it can't be deleted
        """
        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        # Check if this is the only billing address
        if hasattr(self, 'user') and self.user.billing_addresses.count() <= 1:
            return False, "Cannot delete the only billing address"

        # Check if this is the default address and there are other addresses
        if self.is_default and hasattr(self, 'user'):
            other_addresses = self.user.billing_addresses.exclude(pk=self.pk).exists()
            if other_addresses:
                return False, "Set another address as default before deleting this one"

        # Check if this address is used in any orders
        if hasattr(self, 'orders') and self.orders.exists():
            return False, "Cannot delete billing address used in orders"

        return True, ""

    def clean(self):
        """Run model validation before saving."""
        super().clean()

        # Normalize fields
        if self.company_name:
            self.company_name = self.company_name.strip()
        if self.contact_name:
            self.contact_name = self.contact_name.strip()
        if self.tax_id:
            self.tax_id = self.tax_id.strip().upper()  # Normalize tax ID to uppercase
        if self.email:
            self.email = self.email.lower().strip()

        # If this is a business address, ensure company name is set
        if self.is_business and not self.company_name:
            self.company_name = self.contact_name or ""

        # If this is the only address, make it default
        if hasattr(self, 'user') and not self.user.billing_addresses.exists():
            self.is_default = True

    def save(self, *args, **kwargs):
        """Override save to handle default address logic."""
        # If this is being set as default, unset other defaults
        if self.is_default and hasattr(self, 'user'):
            self.user.billing_addresses.exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)
        logger.info(f"BillingAddress {self.pk} saved for user {self.user_id}")