import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxLengthValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel, SlugFieldCommonModel
from common.validators import FileSizeValidator
from orders.enums import OrderStatuses
from orders.models import OrderItem
from products.enums import (ProductCondition, ProductStatus,
                            StockStatus, ProductLabel,
                            ServiceType, ProductType)
from products.managers import (ProductManager, ProductReportManager,
                               ProductAdminManager, ProductVariantManager)
from common.models import AddressBaseModel


logger = logging.getLogger(__name__)


class Location(AddressBaseModel):
    name = models.CharField(
        max_length=100,
        verbose_name=_("Location Name"),
        help_text=_("Name of the location")
    )

    def __str__(self):
        return self.name

    class Meta:
        db_table = "locations"
        verbose_name = _("Location")
        verbose_name_plural = _("Locations")
        indexes = AddressBaseModel.Meta.indexes + [
            models.Index(fields=['name', 'is_deleted']),
            models.Index(fields=['name', 'is_active']),
        ]

    def is_valid(self) -> bool:
        """Check if location is valid for operations.

        Returns:
            bool: True if location is valid, False otherwise
        """
        return (
                super().is_valid() and
                bool(self.name.strip())
        )

    def can_be_deleted(self) -> tuple[bool, str]:
        """Check if location can be safely deleted"""
        if not super().can_be_deleted()[0]:
            return False, super().can_be_deleted()[1]

        order_items = OrderItem.objects.filter(product__location=self)

        can_be_deleted_list = [] # List of cam_be_deleted() booleans for each order item
        for order_item in order_items:
            can_be_deleted, reason = order_item.can_be_deleted()
            can_be_deleted_list.append(can_be_deleted)

        # If there are product and order_items associated with the location any order
        # item cannot be deleted, return False
        if Product.objects.filter(location=self).exists() and order_items.exists() and not all(can_be_deleted_list):
            return False, "Cannot delete location that has active order items associated with it"
        return super().can_be_deleted()


class ProductVariant(CommonModel):
    """
    Product variants with stock management and cost tracking
    """
    objects = ProductVariantManager()

    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        related_name="product_variants"
    )
    sku = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Variant SKU")
    )

    # Cost and pricing
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Cost Price"),
        help_text=_("Actual cost for this specific variant")
    )
    price_adjustment = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.0,
        verbose_name=_("Price Adjustment")
    )

    # Stock management
    stock_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Stock Quantity")
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        verbose_name=_("Low Stock Threshold")
    )

    # Warehouse inventory relationship
    warehouse_inventory = models.ManyToManyField(
        'inventory.WarehouseProfile',
        through='inventory.Inventory',
        related_name='product_variants'
    )

    # Variant attributes
    color = models.CharField(max_length=50, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    material = models.CharField(max_length=50, blank=True, null=True)
    style = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        attributes = []
        if self.color: attributes.append(self.color)
        if self.size: attributes.append(self.size)
        if self.material: attributes.append(self.material)
        if self.style: attributes.append(self.style)

        base = f"{self.product.product_name}"
        if attributes:
            base += f" ({', '.join(attributes)})"
        return base

    class Meta:
        db_table = "product_variants"
        verbose_name = _("Product Variant")
        verbose_name_plural = _("Product Variants")
        ordering = ["product", "color", "size"]
        unique_together = ['product', 'color', 'size', 'material', 'style']
        indexes = CommonModel.Meta.indexes + [
            # Core variant indexes
            models.Index(fields=['product', 'is_deleted', 'is_active']),
            models.Index(fields=['sku', 'is_deleted']),

            # Attribute-based filtering
            models.Index(fields=['color', 'is_deleted']),
            models.Index(fields=['size', 'is_deleted']),
            models.Index(fields=['material', 'is_deleted']),
            models.Index(fields=['style', 'is_deleted']),

            # Inventory management
            models.Index(fields=['stock_quantity', 'is_deleted']),
            models.Index(fields=['product', 'stock_quantity', 'is_deleted']),
            models.Index(fields=['is_deleted', 'stock_quantity', 'is_active']),

            # Price and cost queries
            models.Index(fields=['price_adjustment', 'is_deleted']),
            models.Index(fields=['cost_price', 'is_deleted']),

            # Composite indexes for common queries
            models.Index(fields=['product', 'color', 'size', 'is_deleted']),
            models.Index(fields=['is_deleted', 'is_active', 'stock_quantity']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(stock_quantity__gte=0),
                name="non_negative_stock_quantity"
            ),
            models.CheckConstraint(
                check=models.Q(low_stock_threshold__gte=0),
                name="non_negative_low_stock_threshold"
            ),
        ]

    def is_valid(self) -> bool:
        """
        Check if product variant is valid for sale.

        Returns:
            bool: True if variant is valid for sale, False otherwise with detailed logging
        """
        logger = logging.getLogger(__name__)

        # Basic model validation
        if not super().is_valid():
            logger.warning(f"Variant {self.id} failed basic model validation")
            return False

        # Check if the product is valid and active
        if not self.product or not self.product.is_valid():
            logger.warning(f"Variant {self.id} has an invalid or inactive product")
            return False

        # Check if the variant is active and not deleted
        if not self.is_active or self.is_deleted:
            logger.warning(f"Variant {self.id} is not active or has been deleted")
            return False

        # Check if variant has at least one attribute
        if not any([self.color, self.size, self.material, self.style]):
            logger.warning(
                f"Variant {self.id} is missing required attributes. "
                f"At least one of color, size, material, or style must be set"
            )
            return False

        # Validate SKU
        if not self.sku or not self.sku.strip():
            logger.warning(f"Variant {self.id} has an empty or invalid SKU")
            return False

        # Check for duplicate SKU (case-insensitive)
        duplicate_sku = ProductVariant.objects.filter(
            sku__iexact=self.sku,
            is_deleted=False,
            product_id=self.product_id
        ).exclude(pk=self.pk).exists()

        if duplicate_sku:
            logger.warning(f"Variant {self.id} has a duplicate SKU: {self.sku}")
            return False

        # Price validation
        if not isinstance(self.price_adjustment, (int, float, Decimal)):
            logger.warning(
                f"Variant {self.id} has an invalid price adjustment: {self.price_adjustment}"
            )
            return False

        # For products with inventory tracking
        if self.product.track_inventory:
            if not hasattr(self, 'stock_quantity') or not isinstance(self.stock_quantity, int):
                logger.warning(f"Variant {self.id} has invalid stock quantity")
                return False

            if self.stock_quantity < 0:
                logger.warning(
                    f"Variant {self.id} has negative stock quantity: {self.stock_quantity}"
                )
                return False

            # Check if variant is in stock if required
            if not self.is_in_stock:
                logger.info(f"Variant {self.id} is out of stock")
                return False

        logger.debug(f"Variant {self.id} validation successful")
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if variant can be safely soft-deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """

        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            logger.warning(f"Variant {self.id} cannot be deleted: {reason}")
            return can_delete, reason

        from orders.enums import active_order_statuses


        # Get active order items with this variant
        active_order_items = OrderItem.objects.filter(
            variant=self,
            order__status__in=active_order_statuses
        ).select_related('order').order_by('-order__date_created')[:5]  # Get most recent 5 for logging

        if active_order_items.exists():
            order_ids = [str(item.order.id) for item in active_order_items]
            order_info = ", ".join(order_ids)
            if active_order_items.count() > 5:
                order_info += f" and {active_order_items.count() - 5} more"

            message = (
                f"Cannot delete variant {self.id} as it is associated with active/pending orders. "
                f"Order IDs: {order_info}"
            )
            logger.warning(message)
            return False, message

        # Check if this is the last variant of the product
        if not self.product.has_variants:
            other_variants = ProductVariant.objects.filter(
                product=self.product,
                is_deleted=False,
                is_active=True
            ).exclude(pk=self.pk).exists()

            if not other_variants and self.product.status == ProductStatus.PUBLISHED:
                message = (
                    f"Cannot delete the only variant of published product {self.product_id}. "
                    "The product would be left without any variants."
                )
                logger.warning(message)
                return False, message

        logger.info(f"Variant {self.id} can be safely deleted")
        return True, ""

    def save(self, *args, **kwargs):
        """Override save to handle variant-specific logic"""
        # Ensure price adjustment is a Decimal
        if not isinstance(self.price_adjustment, Decimal):
            try:
                self.price_adjustment = Decimal(str(self.price_adjustment))
            except (TypeError, ValueError, InvalidOperation):
                self.price_adjustment = Decimal('0.00')

        # Ensure stock quantity is an integer
        if hasattr(self, 'stock_quantity') and not isinstance(self.stock_quantity, int):
            try:
                self.stock_quantity = int(self.stock_quantity)
            except (TypeError, ValueError):
                self.stock_quantity = 0

        # Auto-generate SKU if not provided
        if not self.sku and self.product:
            base_sku = self.product.sku or f"PRD{self.product_id:06d}"
            attr_parts = []
            if self.color:
                attr_parts.append(self.color[:3].upper())
            if self.size:
                attr_parts.append(str(self.size).upper())
            if self.material:
                attr_parts.append(self.material[:3].upper())
            if self.style:
                attr_parts.append(self.style[:3].upper())

            self.sku = f"{base_sku}-{'-'.join(attr_parts)}" if attr_parts else f"{base_sku}-VAR"

        super().save(*args, **kwargs)

    @property
    def final_price(self):
        """Calculate final price including base price and adjustment"""
        return self.product.price + self.price_adjustment

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.cost_price and self.final_price and self.cost_price > 0:
            return ((self.final_price - self.cost_price) / self.final_price) * 100
        return None

    @property
    def profit_amount(self):
        """Calculate absolute profit per item"""
        if self.cost_price:
            return self.final_price - self.cost_price
        return None

    @property
    def is_in_stock(self):
        """Check if this variant is in stock"""
        return self.stock_quantity > 0

    @property
    def is_low_stock(self):
        """Check if variant is low in stock"""
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def stock_status(self):
        """Get stock status for this variant"""
        if self.stock_quantity == 0:
            return StockStatus.OUT_OF_STOCK
        elif self.is_low_stock:
            return StockStatus.LOW_STOCK
        else:
            return StockStatus.IN_STOCK

    def reserve_stock(self, quantity):
        """Reserve stock for an order"""
        if quantity > self.stock_quantity:
            raise ValidationError(
                _("Cannot reserve %(quantity)s items. Only %(available)s available.") % {
                    'quantity': quantity,
                    'available': self.stock_quantity
                }
            )

        self.stock_quantity -= quantity
        self.save(update_fields=['stock_quantity', 'date_updated'])

    def release_stock(self, quantity):
        """Release reserved stock back to available"""
        self.stock_quantity += quantity
        self.save(update_fields=['stock_quantity', 'date_updated'])

    def update_stock(self, new_quantity):
        """Update stock quantity"""
        if new_quantity < 0:
            raise ValidationError(_("Stock quantity cannot be negative"))

        self.stock_quantity = new_quantity
        self.save(update_fields=['stock_quantity', 'date_updated'])

    def clean(self):
        """Validate variant data"""
        super().clean()

        # Ensure at least one attribute is set
        if not any([self.color, self.size, self.material, self.style]):
            raise ValidationError(
                _("Variant must have at least one attribute (color, size, material, or style)")
            )

        # Validate SKU uniqueness
        if ProductVariant.objects.filter(
                sku__iexact=self.sku, is_deleted=False
        ).exclude(pk=self.pk).exists():
            raise ValidationError({'sku': _("Variant SKU must be unique")})

        # Validate stock quantity
        if self.stock_quantity < 0:
            raise ValidationError(_("Stock quantity cannot be negative"))


class ProductImage(CommonModel):
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name='product_images',
        verbose_name=_("Product"),
        help_text=_("The product this image belongs to")
    )
    image = models.ImageField(
        upload_to='products/',
        verbose_name=_("Image"),
        help_text=_("Upload a high-quality product image (recommended size: 800x800px, max 5MB)"),
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp']),
            FileSizeValidator(5 * 1024 * 1024)  # 5MB
        ]
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Alt Text"),
        help_text=_("Alternative text for accessibility and SEO (recommended: max 125 characters)"),
        validators=[MaxLengthValidator(200)]
    )
    display_order = models.IntegerField(
        default=0,
        verbose_name=_("Display Order"),
        help_text=_("Order in which images are displayed (lower numbers first)"),
        validators=[MinValueValidator(0)]
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name=_("Primary Image"),
        help_text=_("Set as the main product image (only one image can be primary)")
    )

    class Meta:
        db_table = "product_images"
        verbose_name = _("Product Image")
        verbose_name_plural = _("Product Images")
        ordering = ["display_order", "-date_created"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=['product', 'is_deleted']),
            models.Index(fields=['product', 'display_order', 'is_deleted']),
            models.Index(fields=['is_primary']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'is_primary'],
                condition=models.Q(is_primary=True, is_deleted=False),
                name='unique_primary_image_per_product'
            )
        ]

    def __str__(self):
        return f"Image for {self.product.product_name} (Order: {self.display_order})"

    def clean(self):
        """Additional model validation"""
        super().clean()

        # Ensure only one primary image per product
        if self.is_primary and not self.is_deleted:
            # Check if there's already a primary image for this product
            existing_primary = ProductImage.objects.filter(
                product=self.product,
                is_primary=True,
                is_deleted=False
            ).exclude(pk=self.pk).exists()

            if existing_primary:
                raise ValidationError({
                    'is_primary': _('This product already has a primary image')
                })

    def is_valid(self) -> bool:
        """Check if product image is valid.

        Returns:
            bool: True if image is valid, False otherwise with detailed logging
        """
        logger = logging.getLogger(__name__)

        # Basic model validation
        if not super().is_valid():
            logger.warning(f"Image {self.id} failed basic model validation")
            return False

        # Check required fields
        if not all([self.product, self.image]):
            logger.warning(f"Image {self.id} is missing required fields")
            return False

        # Validate image file
        try:
            # Check if image file exists and is accessible
            if not self.image.storage.exists(self.image.name):
                logger.warning(f"Image file not found: {self.image.name}")
                return False

            # Check image dimensions (min 100x100px)
            from PIL import Image
            with Image.open(self.image) as img:
                width, height = img.size
                if width < 100 or height < 100:
                    logger.warning(
                        f"Image {self.id} dimensions too small: {width}x{height}px "
                        f"(minimum 100x100px)"
                    )
                    return False

                # Check aspect ratio (between 0.5 and 2.0)
                aspect_ratio = width / height
                if not 0.5 <= aspect_ratio <= 2.0:
                    logger.warning(
                        f"Image {self.id} has extreme aspect ratio: {aspect_ratio:.2f} "
                        f"(recommended between 0.5 and 2.0)"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error validating image {self.id}: {str(e)}", exc_info=True)
            return False

        # Validate alt text if provided
        if self.alt_text and len(self.alt_text.strip()) > 200:
            logger.warning(f"Image {self.id} alt text exceeds 200 characters")
            return False

        # If this is set as primary, ensure it's valid
        if self.is_primary and self.is_deleted:
            logger.warning(f"Deleted image {self.id} cannot be set as primary")
            return False

        logger.debug(f"Image {self.id} validation successful")
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if product image can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            logger.warning(f"Image {self.id} cannot be deleted: {reason}")
            return can_delete, reason

        # Check if this is the only image for the product
        other_images = self.product.product_images.filter(
            is_deleted=False
        ).exclude(pk=self.pk)

        if not other_images.exists() and self.product.status == ProductStatus.PUBLISHED:
            message = "Cannot delete the only image of a published product"
            logger.warning(f"{message} (Product ID: {self.product_id})")
            return False, message

        # Check if this is the primary image
        if self.is_primary and other_images.exists():
            # Set another image as primary before deletion
            try:
                new_primary = other_images.first()
                new_primary.is_primary = True
                new_primary.save(update_fields=['is_primary', 'date_updated'])
                logger.info(
                    f"Transferred primary status from image {self.id} to {new_primary.id} "
                    f"for product {self.product_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to transfer primary status from image {self.id}: {str(e)}",
                    exc_info=True
                )
                return False, "Failed to set a new primary image"

        logger.info(f"Image {self.id} can be safely deleted")
        return True, ""

    def save(self, *args, **kwargs):
        """Override save to handle primary image logic"""
        # If this is the first image being added, make it primary
        if not self.pk and not self.is_primary:
            self.is_primary = not self.product.product_images.filter(
                is_primary=True,
                is_deleted=False
            ).exists()

        super().save(*args, **kwargs)

    def img_preview(self):
        """Generate HTML for admin preview"""
        from django.utils.html import format_html
        return format_html(
            '<img src="{}" width="300" height="300" style="object-fit: cover;{}" />',
            self.image.url if self.image else '',
            'opacity: 0.5;' if self.is_deleted else ''
        )

    @property
    def imageURL(self):
        """Get the URL of the image with fallback"""
        try:
            return self.image.url
        except ValueError:
            return f"{settings.MEDIA_ROOT}/products/default-product.png"  # Fallback image

    @property
    def dimensions(self):
        """Get image dimensions if available"""
        try:
            from PIL import Image
            with Image.open(self.image) as img:
                return img.size  # Returns (width, height)
        except:
            return None

    @property
    def file_size_kb(self):
        """Get file size in KB"""
        try:
            return self.image.size / 1024
        except (ValueError, OSError):
            return 0


class Product(SlugFieldCommonModel):
    """
    Base product model - handles product-level information only
    Stock and costs are managed at variant level
    """
    slug_fields = ['product_name', 'uuid']
    objects = ProductManager()
    reports = ProductReportManager()
    admin = ProductAdminManager()

    product_type = models.CharField(
        max_length=20,
        choices=ProductType.choices,
        default=ProductType.PHYSICAL,
        db_index=True,
        verbose_name=_("Product Type")
    )
    product_name = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_("Product Name")
    )

    category = models.ForeignKey(
        "category.Category",
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("Category")
    )
    subcategories = models.ManyToManyField(
        "category.Category",
        related_name="products_subcategories",
        blank=True,
        verbose_name=_("Subcategories")
    )

    # Core pricing (base price for variants)
    price = models.DecimalField(
        default=0.0,
        max_digits=10,
        decimal_places=2,
        db_index=True,
        verbose_name=_("Base Price"),
        help_text=_("Base price for variants")
    )
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Compare At Price"),
        help_text=_("Original price before discount. Used to show the 'was' price when the product is on sale.")
    )

    product_description = models.TextField(
        verbose_name=_("Product Description")
    )

    # Status fields
    condition = models.CharField(
        max_length=20,
        choices=ProductCondition.choices,
        default=ProductCondition.NEW,
        db_index=True,
        verbose_name=_("Product Condition")
    )
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
        db_index=True,
        verbose_name=_("Publication Status")
    )
    stock_status = models.CharField(
        max_length=20,
        choices=StockStatus.choices,
        default=StockStatus.IN_STOCK,
        db_index=True,
        verbose_name=_("Stock Status")
    )
    label = models.CharField(
        max_length=20,
        choices=ProductLabel.choices,
        default=ProductLabel.NONE,
        db_index=True,
        verbose_name=_("Product Label")
    )

    # Inventory settings (not actual quantities)
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        verbose_name=_("Low Stock Threshold")
    )
    track_inventory = models.BooleanField(
        default=True,
        verbose_name=_("Track Inventory")
    )

    # Timed features
    sale_start_date = models.DateTimeField(null=True, blank=True)
    sale_end_date = models.DateTimeField(null=True, blank=True)
    featured_until = models.DateTimeField(null=True, blank=True)

    # Physical product attributes
    weight = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        verbose_name=_("Weight (kg)")
    )
    dimensions = models.CharField(max_length=100, blank=True)
    requires_shipping = models.BooleanField(default=True)
    fragile = models.BooleanField(default=False)
    hazardous = models.BooleanField(default=False)

    # Product identification
    sku = models.CharField(
        max_length=100, unique=True, null=True, blank=True,
        verbose_name=_("Product SKU"),
        help_text=_("Base SKU for products without variants")
    )
    barcode = models.CharField(max_length=100, blank=True, null=True)

    # Manufacturing fields - PRODUCT LEVEL (base manufacturing data)
    manufacturing_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Base Manufacturing Cost"),
        help_text=_("Base cost of manufacturing this product (materials, labor, overhead)")
    )
    packaging_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        default=0.0,
        verbose_name=_("Base Packaging Cost"),
        help_text=_("Base cost of packaging materials for this product")
    )
    shipping_to_warehouse_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        default=0.0,
        verbose_name=_("Base Shipping to Warehouse Cost"),
        help_text=_("Base cost to ship this product from manufacturer to warehouse")
    )
    manufacturing_location = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Manufacturing Location"),
        help_text=_("Primary location where this product is manufactured")
    )
    manufacturing_date = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("Manufacturing Date"),
        help_text=_("Date when this product was first manufactured or produced")
    )
    batch_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Base Batch Number"),
        help_text=_("Primary manufacturing batch or lot number")
    )
    shelf_life = models.DurationField(
        blank=True,
        null=True,
        verbose_name=_("Shelf Life"),
        help_text=_("How long this product remains usable or sellable after manufacturing")
    )

    # Digital product fields
    download_file = models.FileField(upload_to='digital_products/', null=True, blank=True)
    download_limit = models.PositiveIntegerField(default=1)
    access_duration = models.DurationField(null=True, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    file_type = models.CharField(max_length=50, blank=True)

    # Service product fields
    duration = models.DurationField(null=True, blank=True)
    location_required = models.BooleanField(default=False)
    location = models.ForeignKey(
        "Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_products'
    )
    service_type = models.CharField(
        max_length=50, choices=ServiceType.choices, default=ServiceType.CONSULTATION
    )
    provider_notes = models.TextField(blank=True)

    class Meta:
        db_table = 'products'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        indexes = SlugFieldCommonModel.Meta.indexes + [
            # Core indexes
            models.Index(fields=['product_name']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['product_type', 'status']),
            models.Index(fields=['status', 'stock_status']),
            models.Index(fields=['sku']),
            models.Index(fields=['barcode']),

            # Manufacturing indexes
            models.Index(fields=['manufacturing_location']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['manufacturing_date']),
            models.Index(fields=['manufacturing_cost']),

            # Composite manufacturing indexes
            models.Index(fields=['manufacturing_date', 'manufacturing_location']),
            models.Index(fields=['product_type', 'manufacturing_location']),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(price__gte=0), name="non_negative_price"),
            models.CheckConstraint(
                check=(
                        models.Q(compare_at_price__isnull=True) |
                        models.Q(compare_at_price__gte=models.F('price'))
                ),
                name="compare_at_price_gte_price"
            ),
            # Manufacturing constraints
            models.CheckConstraint(check=models.Q(manufacturing_cost__gte=0), name="non_negative_mfg_cost"),
            models.CheckConstraint(check=models.Q(packaging_cost__gte=0), name="non_negative_packaging_cost"),
            models.CheckConstraint(check=models.Q(shipping_to_warehouse_cost__gte=0), name="non_negative_ship_cost"),
            models.CheckConstraint(
                check=models.Q(shelf_life__gt=timedelta(seconds=0)) | models.Q(shelf_life__isnull=True),
                name="positive_shelf_life"
            ),
        ]
        ordering = ['product_name']

    def save(self, *args, **kwargs):
        # Auto-update stock_status based on variants
        if self.track_inventory and getattr(self, "has_variants", False) and self.has_variants:
            total_stock = self.total_stock_quantity
            if total_stock == 0:
                self.stock_status = StockStatus.OUT_OF_STOCK
            elif total_stock <= self.low_stock_threshold:
                self.stock_status = StockStatus.LOW_STOCK
            else:
                self.stock_status = StockStatus.IN_STOCK

        # Handle digital products
        if not self.track_inventory:
            self.stock_status = StockStatus.IN_STOCK

        super().save(*args, **kwargs)

    def is_valid(self) -> bool:
        """Check if product is valid for sale.

        Returns:
            bool: True if product is valid for sale, False otherwise with detailed logging
        """
        logger = logging.getLogger(__name__)

        # Basic model validation
        if not super().is_valid():
            logger.warning(f"Product {self.id} failed basic model validation")
            return False

        # Required fields validation
        required_fields = {
            'product_name': self.product_name,
            'product_description': self.product_description,
            'category': self.category
        }

        for field, value in required_fields.items():
            if not value or (isinstance(value, str) and not value.strip()):
                logger.warning(f"Product {self.id} is missing required field: {field}")
                return False

        # Status check
        if self.status != ProductStatus.PUBLISHED:
            logger.info(f"Product {self.id} is not published (status: {self.status})")
            return False

        # Price validation
        if not isinstance(self.price, (int, float, Decimal)) or self.price <= 0:
            logger.warning(f"Product {self.id} has invalid price: {self.price}")
            return False

        # Digital product validation
        if self.product_type == ProductType.DIGITAL:
            if not self.download_file:
                logger.warning(f"Digital product {self.id} is missing download file")
                return False
            if not self.file_size or self.file_size <= 0:
                logger.warning(f"Digital product {self.id} has invalid file size")
                return False

        # Service product validation
        if self.product_type == ProductType.SERVICE:
            if (self.location_required and
                    self.service_type in [ServiceType.CONSULTATION, ServiceType.REPAIR,
                                          ServiceType.TRAINING, ServiceType.INSTALLATION] and
                    not self.location):
                logger.warning(f"Service product {self.id} requires a location but none is set")
                return False

        # Variant validation
        if self.has_variants:
            active_variants = self.product_variants.filter(is_deleted=False, is_active=True)
            if not active_variants.exists():
                logger.warning(f"Product {self.id} has no active variants")
                return False

            valid_variants = [v for v in active_variants if v.is_valid()]
            if not valid_variants:
                logger.warning(f"Product {self.id} has no valid variants")
                return False

            logger.debug(f"Product {self.id} has {len(valid_variants)} valid variants")
        else:
            # Simple product stock validation
            if self.track_inventory and not self.total_stock_quantity > 0:
                logger.warning(f"Product {self.id} is out of stock and track_inventory is enabled")
                return False

        # Expiration check
        if self.is_expired:
            logger.info(f"Product {self.id} has expired")
            return False

        logger.debug(f"Product {self.id} validation successful")
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if product can be safely soft-deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        logger = logging.getLogger(__name__)

        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            logger.warning(f"Product {self.id} cannot be deleted: {reason}")
            return can_delete, reason

        # Check for active variants
        active_variants = self.product_variants.filter(is_deleted=False, is_active=True)
        if self.has_variants and active_variants.exists():
            variant_info = ", ".join(str(v.id) for v in active_variants[:3])
            if active_variants.count() > 3:
                variant_info += f" and {active_variants.count() - 3} more"
            message = f"Cannot delete product {self.id} with active variants: {variant_info}"
            logger.warning(message)
            return False, message

        # Check variant-specific constraints
        for variant in active_variants:
            can_delete, reason = variant.can_be_deleted()
            if not can_delete:
                logger.warning(f"Product {self.id} has variant {variant.id} that cannot be deleted: {reason}")
                return False, f"Variant {variant.id}: {reason}"

        # Check for active promotions
        if hasattr(self, 'coupons'):
            active_coupons = self.coupons.filter(
                is_active=True,
                end_date__gte=timezone.now()
            )
            if active_coupons.exists():
                coupon_info = ", ".join(c.coupon_code for c in active_coupons[:3])
                if active_coupons.count() > 3:
                    coupon_info += f" and {active_coupons.count() - 3} more"
                message = f"Cannot delete product {self.id} with active coupons: {coupon_info}"
                logger.warning(message)
                return False, message

        # Check for active orders
        if hasattr(self, 'order_items'):
            from orders.enums import active_order_statuses
            active_orders = self.order_items.filter(
                order__status__in=active_order_statuses
            ).select_related('order').distinct('order')

            if active_orders.exists():
                order_info = ", ".join(str(o.order.id) for o in active_orders[:3])
                if active_orders.count() > 3:
                    order_info += f" and {active_orders.count() - 3} more"
                message = f"Cannot delete product {self.id} with active orders: {order_info}"
                logger.warning(message)
                return False, message

        logger.info(f"Product {self.id} can be safely deleted")
        return True, ""

    @property
    def total_stock_quantity(self):
        """Aggregate stock from all variants"""
        return self.product_variants.filter(
            is_deleted=False, is_active=True
        ).aggregate(total=models.Sum('stock_quantity'))['total'] or 0

    @property
    def has_variants(self):
        """Check if product has any active variants"""
        return (getattr(self, "product_variants", False) and
                self.product_variants.filter(is_deleted=False, is_active=True).exists())

    @property
    def is_expired(self) -> bool:
        """Check if product has expired based on manufacturing date and shelf life"""
        if not self.manufacturing_date or not self.shelf_life:
            return False

        from django.utils import timezone
        expiration_date = self.manufacturing_date + self.shelf_life
        return timezone.now().date() > expiration_date

    @property
    def is_digital(self):
        return self.product_type == ProductType.DIGITAL

    @property
    def days_until_expiry(self) -> int:
        """Get number of days until product expires"""
        if not self.manufacturing_date or not self.shelf_life:
            return None

        from django.utils import timezone
        expiration_date = self.manufacturing_date + self.shelf_life
        today = timezone.now().date()
        return (expiration_date - today).days

    @property
    def is_on_sale(self):
        """Check if product is currently on sale"""
        from django.utils import timezone
        now = timezone.now()
        return (
                self.compare_at_price and
                self.compare_at_price > self.price and
                (not self.sale_start_date or self.sale_start_date <= now) and
                (not self.sale_end_date or self.sale_end_date >= now)
        )

    @property
    def total_manufacturing_cost(self) -> Decimal:
        """Get total manufacturing-related costs"""
        return self._calculate_estimated_cost_price()

    def _can_calculate_cost_price(self) -> bool:
        """
        Check if we have enough manufacturing data to estimate cost price.
        """
        return self.manufacturing_cost is not None and self.manufacturing_cost > 0

    def _calculate_estimated_cost_price(self) -> Decimal:
        """
        Calculate estimated cost price based on manufacturing data.

        Formula: manufacturing_cost + packaging_cost + shipping_to_warehouse_cost
        """
        base_cost = self.manufacturing_cost or Decimal('0.0')
        packaging = self.packaging_cost or Decimal('0.0')
        shipping = self.shipping_to_warehouse_cost or Decimal('0.0')

        total_cost = base_cost + packaging + shipping

        # Add a small margin for handling and storage if we have basic data
        if base_cost > 0:
            total_cost *= Decimal('1.05')  # 5% handling/storage margin

        return total_cost.quantize(Decimal('0.01'))  # Round to 2 decimal places

    def get_manufacturing_info(self) -> dict:
        """Get comprehensive manufacturing information"""
        return {
            'manufacturing_cost': float(self.manufacturing_cost) if self.manufacturing_cost else None,
            'packaging_cost': float(self.packaging_cost) if self.packaging_cost else None,
            'shipping_to_warehouse_cost': float(
                self.shipping_to_warehouse_cost) if self.shipping_to_warehouse_cost else None,
            'total_cost': float(self.total_manufacturing_cost),
            'manufacturing_location': self.manufacturing_location,
            'manufacturing_date': self.manufacturing_date,
            'batch_number': self.batch_number,
            'shelf_life_days': self.shelf_life.days if self.shelf_life else None,
            'is_expired': self.is_expired,
            'days_until_expiry': self.days_until_expiry,
        }

    @property
    def final_price(self):
        """
        Return price range for products with variants, or base price for simple products
        """
        if self.has_variants:
            price_range = self.get_variant_price_range()
            return price_range
        return float(self.price)

    def get_variant_price_range(self):
        """Calculate min/max prices across all variants"""
        from django.db.models import Min, Max

        result = self.product_variants.filter(
            is_deleted=False, is_active=True
        ).aggregate(
            min_adjustment=Min('price_adjustment'),
            max_adjustment=Max('price_adjustment')
        )

        base_price = float(self.price)
        min_final = base_price + float(result['min_adjustment'] or 0)
        max_final = base_price + float(result['max_adjustment'] or 0)

        return {
            'min': min_final,
            'max': max_final,
            'has_variation': min_final != max_final
        }

    def get_available_variants(self):
        """Get all active variants with stock information"""
        return self.product_variants.filter(
            is_deleted=False, is_active=True
        ).select_related('product')

    def validate_purchase(self, quantity=1, color=None, size=None):
        """Validate if product can be purchased"""
        if self.is_expired:
            raise ValidationError(_("This product has expired and cannot be sold."))

        if self.has_variants:
            if not color and not size:
                raise ValidationError(_("Please select a variant for this product"))

            try:
                variant = self.product_variants.get(
                    color=color, size=size, is_deleted=False, is_active=True
                )
                if variant.stock_quantity < quantity:
                    raise ValidationError(
                        _("Insufficient stock. Only %(stock)s available.") %
                        {'stock': variant.stock_quantity}
                    )
            except ProductVariant.DoesNotExist:
                raise ValidationError(_("Selected variant is not available"))
        else:
            # For products without variants, check product-level stock
            if self.track_inventory and self.total_stock_quantity < quantity:
                raise ValidationError(_("Insufficient stock"))

        return True

    def clean(self):
        """Validation"""
        super().clean()

        # Validate sale dates
        if self.sale_start_date and self.sale_end_date:
            if self.sale_start_date >= self.sale_end_date:
                raise ValidationError(_("Sale end date must be after start date"))

        # Validate digital product fields
        if self.product_type == ProductType.DIGITAL:
            if not self.download_file:
                raise ValidationError(_("Digital products require a download file"))

        # Validate manufacturing date is not in the future
        if self.manufacturing_date and self.manufacturing_date > timezone.now().date():
            raise ValidationError({
                'manufacturing_date': _("Manufacturing date cannot be in the future")
            })

        # Validate costs are not negative
        cost_fields = ['manufacturing_cost', 'packaging_cost', 'shipping_to_warehouse_cost']
        for field in cost_fields:
            value = getattr(self, field)
            if value is not None and value < 0:
                raise ValidationError({field: _(f"{field.replace('_', ' ').title()} cannot be negative")})
