import logging
import uuid

from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from phonenumber_field.modelfields import PhoneNumberField

from cart.managers import CartItemManager
from common.managers import SoftDeleteManger


logger = logging.getLogger(__name__)


class CommonModel(models.Model):
    objects = SoftDeleteManger()
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

    def delete(self, *args, **kwargs):
        """Soft delete: mark as deleted, cascade to related objects."""
        if self.is_deleted:
            return  # Already deleted

        self.is_deleted = True
        self.is_active = False
        self.date_deleted = timezone.now()
        self.save(update_fields=["is_deleted", "is_active", "date_deleted"])

        # Soft cascade: mark related CASCADE FKs as deleted too
        for rel in self._meta.related_objects:
            if rel.on_delete == models.CASCADE:
                related_manager = getattr(self, rel.get_accessor_name(), None)
                if related_manager and hasattr(related_manager, 'all'):
                    # Only call .all() if it's a manager (not a single related object)
                    qs = related_manager.all()
                    for obj in qs:
                        if isinstance(obj, CommonModel):
                            obj.delete()

    def hard_delete(self, *args, **kwargs):
        return super().delete(*args, **kwargs)

    def restore(self):
        """Restore soft-deleted instance"""
        self.is_deleted = False
        self.is_active = True
        self.deleted_at = None
        self.save()


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


class ItemCommonModel(CommonModel):
    """Item model base for models like CartItem, OrderItem etc. Represents a product"""

    objects = CartItemManager()

    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(help_text=_("Quantity of the product"), default=1)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,
                                      help_text=_("Total price of the product"))

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

    @property
    def item_final_price(self) -> float:
        """Final price for this item, taking variant into account"""
        if self.variant:
            return float(self.variant.final_price)
        if self.product:
            return self.product.get_price_for_variant(
                color=getattr(self.variant, 'color', None),
                size=getattr(self.variant, 'size', None)
            )
        return 0.0

    def save(self, *args, **kwargs):
        """Automatically calculate total price before saving"""
        price = Decimal(str(self.item_final_price or 0))
        quantity = Decimal(str(self.quantity or 0))
        self.total_price = price * quantity
        super().save(*args, **kwargs)


class SlugFieldCommonModel(CommonModel):
    """Common model for models with slug field"""
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

    def generate_unique_slug(self, fields_to_slugify: list[str]) -> Optional[str]:
        field_values = []
        for field in fields_to_slugify:
            value = getattr(self, field, None)
            if callable(value):
                value = value()
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
        super().save(*args, **kwargs)
        if is_new or not self.slug:
            # Customize fields used to generate slug per model
            fields_to_slugify = getattr(self, "slug_fields", ["slug"])  # default fallback
            self._generate_and_set_slug(fields_to_slugify)


class ShippingAddress(AddressBaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
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
        verbose_name = "Shipping AddressBaseModel"
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
        constraints = [
            # Ensure only one default address per user
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_default=True, is_deleted=False),
                name='unique_default_shipping_address'
            )
        ]


class BillingAddress(AddressBaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
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
        verbose_name = "Billing AddressBaseModel"
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
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_default=True, is_deleted=False),
                name='unique_default_billing_address'
            )
        ]