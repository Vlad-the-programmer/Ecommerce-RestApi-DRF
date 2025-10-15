import logging
from datetime import timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel
from common.utils import generate_unique_slug
from products.enums import (ProductCondition, ProductStatus,
                            StockStatus, ProductLabel,
                            ServiceType, ProductType)
from products.managers import (ProductManager, ProductReportManager,
                               ProductAdminManager, ProductVariantManager)

logger = logging.getLogger(__name__)


class ProductVariant(CommonModel):
    """
    Unified variant system to handle all combinations
    """
    objects = ProductVariantManager()

    product = models.ForeignKey("Product", on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Variant SKU"),
        help_text=_("Unique Stock Keeping Unit for this specific variant")
    )
    price_adjustment = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.0,
        verbose_name=_("Price Adjustment"),
        help_text=_("Additional price for this variant (can be negative for discounts)")
    )
    stock_quantity = models.IntegerField(
        default=0,
        verbose_name=_("Variant Stock"),
        help_text=_("Stock quantity for this specific variant")
    )

    # Attributes
    color = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Color"),
        help_text=_("Color variant (e.g., Red, Blue, Green)")
    )
    size = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Size"),
        help_text=_("Size variant (e.g., Small, Medium, Large)")
    )

    def __str__(self):
        base = f"{self.product.product_name}"
        attributes = []
        if self.color:
            attributes.append(self.color)
        if self.size:
            attributes.append(self.size)
        if attributes:
            base += f" ({', '.join(attributes)})"
        return base

    @property
    def final_price(self):
        """Calculate final price including base price and adjustment"""
        return self.product.price + self.price_adjustment

    @property
    def is_in_stock(self):
        """Check if this variant is in stock"""
        return self.stock_quantity > 0

    def clean(self):
        """Validate variant data"""
        super().clean()

        # Ensure at least one attribute is set
        if not self.color and not self.size:
            raise ValidationError(_("Variant must have at least one attribute (color or size)"))

        # Validate SKU uniqueness across variants
        if ProductVariant.objects.filter(
                sku=self.sku,
                is_deleted=False
        ).exclude(pk=self.pk).exists():
            raise ValidationError({'sku': _("Variant SKU must be unique")})

    class Meta:
        db_table = "product_variants"
        verbose_name = _("Product Variant")
        verbose_name_plural = _("Product Variants")
        ordering = ["-date_created"]
        unique_together = ['product', 'color', 'size']
        indexes = CommonModel.Meta.indexes + [
            # Core variant indexes
            models.Index(fields=['product', 'is_deleted']),
            models.Index(fields=['sku', 'is_deleted']),

            # Attribute-based filtering
            models.Index(fields=['color', 'is_deleted']),
            models.Index(fields=['size', 'is_deleted']),
            models.Index(fields=['product', 'color', 'size', 'is_deleted']),

            # Inventory management
            models.Index(fields=['stock_quantity', 'is_deleted']),
            models.Index(fields=['product', 'stock_quantity', 'is_deleted']),

            # Price-based queries
            models.Index(fields=['price_adjustment', 'is_deleted']),
        ]


class ProductImage(CommonModel):
    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
        related_name='product_images'
    )
    image = models.ImageField(
        upload_to='products/',
        verbose_name=_("Image"),
        help_text=_("Product image for display")
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Alt Text"),
        help_text=_("Alternative text for accessibility and SEO")
    )
    display_order = models.IntegerField(
        default=0,
        verbose_name=_("Display Order"),
        help_text=_("Order in which images are displayed (lower numbers first)")
    )

    def img_preview(self):
        return mark_safe(f'<img src="{self.imageURL}" width="300" height="300" style="object-fit: cover;"/>')

    @property
    def imageURL(self):
        try:
            url = self.image.url
        except:
            url = ''
        return url

    class Meta(CommonModel.Meta):
        db_table = "product_images"
        verbose_name = _("Product Image")
        verbose_name_plural = _("Product Images")
        ordering = ["display_order", "-date_created"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=['product', 'is_deleted']),
            models.Index(fields=['product', 'display_order', 'is_deleted']),
        ]


class Product(CommonModel):
    """
    Abstract base product model with common fields and methods.
    Specialized product types should inherit from this.
    """

    objects = ProductManager()
    reports = ProductReportManager()
    admin = ProductAdminManager()

    parent = models.ForeignKey(
        'self',
        related_name='variants',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text=_("Parent product for product variants"),
        verbose_name=_("Parent Product")
    )
    product_type = models.CharField(
        max_length=20,
        choices=ProductType.choices,
        default=ProductType.PHYSICAL,
        db_index=True,
        help_text=_("Type of product determines how it's handled and delivered"),
        verbose_name=_("Product Type")
    )
    product_name = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_("Product Name"),
        help_text=_("Name of the product as displayed to customers")
    )
    slug = models.SlugField(
        unique=True,
        max_length=255,
        blank=True,
        verbose_name=_("URL Slug"),
        help_text=_("Unique URL-friendly identifier for the product")
    )
    category = models.ForeignKey(
        "category.Category",
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name=_("Category"),
        help_text=_("Main category for organizing products")
    )

    # Core product information
    price = models.DecimalField(
        default=0.0,
        max_digits=10,
        decimal_places=2,
        db_index=True,
        verbose_name=_("Selling Price"),
        help_text=_("Current selling price displayed to customers")
    )
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Compare At Price"),
        help_text=_("Original price before discount for showing savings")
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Cost Price"),
        help_text=_("Total cost to acquire or produce this item for profit calculations")
    )

    product_description = models.TextField(
        verbose_name=_("Product Description"),
        help_text=_("Detailed description of the product features and specifications")
    )

    # Separate status fields
    condition = models.CharField(
        max_length=20,
        choices=ProductCondition.choices,
        default=ProductCondition.NEW,
        db_index=True,
        verbose_name=_("Product Condition"),
        help_text=_("Physical condition of the product")
    )
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
        db_index=True,
        verbose_name=_("Publication Status"),
        help_text=_("Current publication status in the store")
    )
    stock_status = models.CharField(
        max_length=20,
        choices=StockStatus.choices,
        default=StockStatus.IN_STOCK,
        db_index=True,
        verbose_name=_("Stock Status"),
        help_text=_("Current availability status based on inventory")
    )
    label = models.CharField(
        max_length=20,
        choices=ProductLabel.choices,
        default=ProductLabel.NONE,
        db_index=True,
        verbose_name=_("Product Label"),
        help_text=_("Marketing label for highlighting products")
    )

    # Quantitative fields
    stock_quantity = models.IntegerField(
        default=0,
        verbose_name=_("Stock Quantity"),
        help_text=_("Current number of items available in inventory")
    )
    low_stock_threshold = models.IntegerField(
        default=5,
        verbose_name=_("Low Stock Threshold"),
        help_text=_("Minimum stock level before low stock alerts")
    )

    # Timed features
    sale_start_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Sale Start Date"),
        help_text=_("Date and time when the sale price becomes active")
    )
    sale_end_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Sale End Date"),
        help_text=_("Date and time when the sale price expires")
    )
    featured_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Featured Until"),
        help_text=_("Date when the product will no longer be featured")
    )
    track_inventory = models.BooleanField(
        default=True,
        verbose_name=_("Track Inventory"),
        help_text=_("Enable inventory tracking and stock level management")
    )

    def save(self, *args, **kwargs):

        # Auto-update stock_status based on variants or direct quantity
        if self.track_inventory:
            if self.has_variants():
                # Update product stock status based on variants
                total_stock = self.variants.filter(is_deleted=False).aggregate(
                    total=models.Sum('stock_quantity')
                )['total'] or 0
                self.stock_quantity = total_stock
            else:
                # For products without variants, use direct quantity
                total_stock = self.stock_quantity

            self.stock_status = StockStatus.IN_STOCK if total_stock > 0 else StockStatus.OUT_OF_STOCK

        # Calculate cost price if not set and we have sufficient data
        if not self.cost_price and self._can_calculate_cost_price():
            self.cost_price = self._calculate_estimated_cost_price()

        super().save(*args, **kwargs)

        # Generate unique slug ONLY if slug is empty AND we have product_name
        # Do this only after the first save to ensure UUID is available
        if not self.slug and self.product_name:
            self._generate_and_set_slug()

    def _generate_and_set_slug(self):
        """Generate and set slug without causing infinite save loop"""
        generated_slug = generate_unique_slug(Product, self, fields_to_slugify=["product_name"])

        if generated_slug:
            # Use update() to avoid recursive save
            Product.objects.filter(pk=self.pk).update(slug=generated_slug)
            # Update the current instance
            self.slug = generated_slug
        else:
            # Fallback slug generation using UUID
            fallback_slug = slugify(f"product-{self.uuid}")
            Product.objects.filter(pk=self.pk).update(slug=fallback_slug)
            self.slug = fallback_slug

        logger.info(f"Set slug '{self.slug}' for product {self.pk}")


    def _can_calculate_cost_price(self):
        """Check if we have enough data to estimate cost price"""
        return False

    def _calculate_estimated_cost_price(self):
        """Calculate estimated cost price based on available data"""
        return Decimal('0.0')

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.cost_price and self.price and self.cost_price > 0:
            return ((self.price - self.cost_price) / self.price) * 100
        return None

    @property
    def profit_amount(self):
        """Calculate absolute profit per item"""
        if self.cost_price and self.price:
            return self.price - self.cost_price
        return None

    @property
    def margin_tier(self):
        """Categorize profit margin into tiers"""
        margin = self.profit_margin
        if margin is None:
            return "unknown"
        elif margin < 10:
            return "low"
        elif margin < 30:
            return "medium"
        elif margin < 50:
            return "high"
        else:
            return "premium"

    def delete(self, *args, **kwargs):
        self.status = ProductStatus.DELETED
        super().delete(*args, **kwargs)

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
    def is_featured(self):
        """Check if product is currently featured"""
        from django.utils import timezone
        now = timezone.now()
        return (
                self.label == ProductLabel.FEATURED or
                (self.featured_until and self.featured_until >= now)
        )

    @property
    def discount_percentage(self):
        """Calculate discount percentage"""
        if self.is_on_sale and self.compare_at_price:
            discount = ((self.compare_at_price - self.price) / self.compare_at_price) * 100
            return round(discount, 1)
        return 0

    @property
    def is_low_stock(self):
        """Check if product is low in stock"""
        return self.stock_quantity <= self.low_stock_threshold

    def has_variants(self):
        """Check if product has any variants"""
        return self.variants.filter(is_deleted=False).exists()

    def get_available_variants_info(self):
        """Get normalized variant information"""
        variants = self.variants.filter(is_deleted=False)

        colors = variants.exclude(color__isnull=True).values_list(
            'color', flat=True
        ).distinct()

        sizes = variants.exclude(size__isnull=True).values_list(
            'size', flat=True
        ).distinct()

        price_range = self.get_variant_price_range()

        return {
            'available_colors': list(colors),
            'available_sizes': list(sizes),
            'variants_count': variants.count(),
            'price_range': price_range,
            'in_stock_variants': variants.filter(stock_quantity__gt=0).count(),
        }

    def get_variant_price_range(self):
        """Calculate min/max prices across all variants"""
        from django.db.models import Min, Max

        result = self.variants.filter(is_deleted=False).aggregate(
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

    def get_final_price_with_variants(self, color=None, size=None):
        """Calculate final price with selected variants"""
        final_price = float(self.price)
        selected_variants = {}

        if color or size:
            try:
                variant = self.variants.get(
                    color=color,
                    size=size,
                    is_deleted=False
                )
                final_price += float(variant.price_adjustment)
                selected_variants = {
                    'color': variant.color,
                    'size': variant.size,
                    'sku': variant.sku,
                    'price_adjustment': float(variant.price_adjustment)
                }
            except ProductVariant.DoesNotExist:
                # If exact combination not found, try to find closest match
                pass

        return {
            'final_price': final_price,
            'selected_variants': selected_variants,
            'base_price': float(self.price),
            'total_adjustments': final_price - float(self.price)
        }

    def validate_variant_combination(self, color=None, size=None):
        """Validate if a variant combination is available"""
        errors = []

        if color or size:
            exists = self.variants.filter(
                color=color,
                size=size,
                is_deleted=False
            ).exists()
            if not exists:
                errors.append("Selected variant combination is not available")

        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }

    def get_variant_display_name(self, color=None, size=None):
        """Generate display name with selected variants"""
        base_name = self.product_name
        variant_parts = []

        if color:
            variant_parts.append(color)
        if size:
            variant_parts.append(size)

        if variant_parts:
            return f"{base_name} ({', '.join(variant_parts)})"

        return base_name

    def get_delivery_info(self):
        """Abstract method to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement get_delivery_info()")

    def validate_purchase(self, quantity=1, color=None, size=None):
        """Abstract method to validate purchase"""
        raise NotImplementedError("Subclasses must implement validate_purchase()")

    def __str__(self) -> str:
        return f"{self.product_name} ({self.get_product_type_display()})"

    class Meta:
        abstract = True
        ordering = ['product_name']
        indexes = CommonModel.Meta.indexes + [
            # Core product identity
            models.Index(fields=['slug', 'is_deleted']),
            models.Index(fields=['product_name', 'is_deleted']),

            # Category navigation
            models.Index(fields=['category', 'is_deleted']),
            models.Index(fields=['category', 'status', 'is_deleted']),
            models.Index(fields=['category', 'product_type', 'is_deleted']),

            # Price and financial queries
            models.Index(fields=['price', 'is_deleted']),
            models.Index(fields=['price', 'category', 'is_deleted']),
            models.Index(fields=['compare_at_price', 'is_deleted']),
            models.Index(fields=['cost_price', 'is_deleted']),

            # Status-based filtering
            models.Index(fields=['status', 'is_deleted']),
            models.Index(fields=['stock_status', 'is_deleted']),
            models.Index(fields=['condition', 'is_deleted']),
            models.Index(fields=['label', 'is_deleted']),
            models.Index(fields=['product_type', 'is_deleted']),

            # Inventory management
            models.Index(fields=['stock_quantity', 'is_deleted']),
            models.Index(fields=['stock_status', 'stock_quantity', 'is_deleted']),

            # Marketing and promotions
            models.Index(fields=['label', 'status', 'is_deleted']),
            models.Index(fields=['is_deleted', 'label', 'status']),

            # Time-based features
            models.Index(fields=['sale_start_date', 'sale_end_date', 'is_deleted']),
            models.Index(fields=['featured_until', 'is_deleted']),
            models.Index(fields=['date_created', 'is_deleted']),

            # Composite queries for catalog
            models.Index(fields=['status', 'stock_status', 'category', 'is_deleted']),
            models.Index(fields=['status', 'product_type', 'category', 'is_deleted']),
            models.Index(fields=['status', 'price', 'category', 'is_deleted']),
        ]


class PhysicalProduct(Product):
    """
    Physical product that requires shipping
    """
    weight = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Weight"),
        help_text=_("Product weight in kilograms (kg) for shipping calculations")
    )
    dimensions = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Dimensions"),
        help_text=_("Product dimensions in centimeters. Format: Length×Width×Height (e.g., 30×20×10)")
    )
    requires_shipping = models.BooleanField(
        default=True,
        verbose_name=_("Requires Shipping"),
        help_text=_("Whether this product requires physical shipping or is pickup-only")
    )
    shipping_class = models.ForeignKey(
        'shipping.ShippingClass',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Shipping Class"),
        help_text=_("Shipping class used for calculating shipping rates and delivery times")
    )
    fragile = models.BooleanField(
        default=False,
        verbose_name=_("Fragile Item"),
        help_text=_("Whether this product requires special fragile handling during shipping")
    )
    hazardous = models.BooleanField(
        default=False,
        verbose_name=_("Hazardous Material"),
        help_text=_("Whether this product contains hazardous materials requiring special shipping")
    )

    # Inventory tracking
    sku = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("SKU"),
        help_text=_("Stock Keeping Unit - unique identifier for inventory management")
    )
    barcode = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Barcode"),
        help_text=_("Barcode number (UPC, EAN, ISBN) for scanning and inventory tracking")
    )

    # Manufacturing fields
    manufacturing_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Manufacturing Cost"),
        help_text=_("Direct cost of manufacturing this product (materials, labor, overhead)")
    )
    packaging_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        default=0.0,
        verbose_name=_("Packaging Cost"),
        help_text=_("Cost of packaging materials for this product")
    )
    shipping_to_warehouse_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        default=0.0,
        verbose_name=_("Shipping to Warehouse Cost"),
        help_text=_("Cost to ship this product from manufacturer to your warehouse")
    )
    manufacturing_location = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("Manufacturing Location"),
        help_text=_("Location where this product is manufactured (country, city, or factory)")
    )
    manufacturing_date = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("Manufacturing Date"),
        help_text=_("Date when this product was manufactured or produced")
    )
    batch_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Batch Number"),
        help_text=_("Manufacturing batch or lot number for quality control")
    )
    shelf_life = models.DurationField(
        blank=True,
        null=True,
        verbose_name=_("Shelf Life"),
        help_text=_("How long this product remains usable or sellable after manufacturing")
    )

    def _can_calculate_cost_price(self) -> bool:
        """
        Check if we have enough manufacturing data to estimate cost price.
        Overrides the base class method.
        """
        return self.manufacturing_cost is not None and self.manufacturing_cost > 0

    def _calculate_estimated_cost_price(self) -> Decimal:
        """
        Calculate estimated cost price based on manufacturing data.
        Overrides the base class method.

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

    @property
    def total_manufacturing_cost(self) -> Decimal:
        """Get total manufacturing-related costs"""
        return self._calculate_estimated_cost_price()

    @property
    def is_expired(self) -> bool:
        """Check if product has expired based on manufacturing date and shelf life"""
        if not self.manufacturing_date or not self.shelf_life:
            return False

        from django.utils import timezone
        expiration_date = self.manufacturing_date + self.shelf_life
        return timezone.now().date() > expiration_date

    @property
    def days_until_expiry(self) -> int:
        """Get number of days until product expires"""
        if not self.manufacturing_date or not self.shelf_life:
            return None

        from django.utils import timezone
        expiration_date = self.manufacturing_date + self.shelf_life
        today = timezone.now().date()
        return (expiration_date - today).days

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

    def get_delivery_info(self):
        """Get comprehensive delivery information for physical product"""
        base_info = {
            'product_id': self.uuid,
            'product_name': self.product_name,
            'product_type': self.get_product_type_display(),
            'price': float(self.price),
            'stock_status': self.get_stock_status_display(),
            'available_variants': self.get_available_variants_info(),
            'price_range': self.get_variant_price_range(),
        }

        # Add physical product specific delivery info
        base_info.update({
            'requires_shipping': self.requires_shipping,
            'weight': float(self.weight) if self.weight else None,
            'dimensions': self.dimensions,
            'fragile': self.fragile,
            'hazardous': self.hazardous,
            'shipping_class': str(self.shipping_class) if self.shipping_class else None,
            'estimated_delivery': self.get_estimated_delivery_time(),
            'delivery_type': 'shipping',
            'is_expired': self.is_expired,
            'days_until_expiry': self.days_until_expiry,
        })
        return base_info

    def get_estimated_delivery_time(self) -> str:
        """Calculate estimated delivery time based on shipping class"""
        if self.shipping_class and hasattr(self.shipping_class, 'get_estimated_delivery'):
            return self.shipping_class.get_estimated_delivery()
        return "5-7 business days"  # Default fallback

    def validate_purchase(self, quantity: int = 1, color=None, size=None):
        """
        Validate if this physical product can be purchased in the requested quantity.
        Overrides the base class method.
        """
        # First, validate inventory and variants using parent method
        super().validate_purchase(quantity, color, size)

        # Additional validation for physical products
        if self.is_expired:
            raise ValidationError(_("This product has expired and cannot be sold."))

        if self.hazardous:
            # You could add logic to check shipping restrictions based on destination
            # For example: validate_hazardous_shipping(destination_country)
            # For now, just log or handle as needed
            pass

        return True

    def clean(self):
        """Additional validation for physical product specifics"""
        super().clean()

        # Validate weight
        if self.weight is not None and self.weight < 0:
            raise ValidationError({'weight': _("Weight cannot be negative")})

        # Validate dimensions format
        if self.dimensions:
            import re
            if not re.match(r'^\d+(\.\d+)?×\d+(\.\d+)?×\d+(\.\d+)?$', self.dimensions):
                raise ValidationError({
                    'dimensions': _("Dimensions must be in format: Length×Width×Height (e.g., 30×20×10)")
                })

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

    def __str__(self):
        base_str = super().__str__()
        if self.sku:
            return f"{base_str} [{self.sku}]"
        return base_str

    class Meta(Product.Meta):
        db_table = "physical_products"
        verbose_name = _("Physical Product")
        verbose_name_plural = _("Physical Products")
        indexes = Product.Meta.indexes + [
            # Inventory & SKU indexes
            models.Index(fields=['sku', 'is_deleted']),
            models.Index(fields=['barcode', 'is_deleted']),
            models.Index(fields=['track_inventory', 'is_deleted']),

            # Manufacturing indexes
            models.Index(fields=['manufacturing_date', 'is_deleted']),
            models.Index(fields=['manufacturing_location', 'is_deleted']),
            models.Index(fields=['batch_number', 'is_deleted']),

            # Shipping & logistics indexes
            models.Index(fields=['requires_shipping', 'is_deleted']),
            models.Index(fields=['shipping_class', 'is_deleted']),
            models.Index(fields=['weight', 'is_deleted']),
            models.Index(fields=['fragile', 'is_deleted']),
            models.Index(fields=['hazardous', 'is_deleted']),

            # Composite manufacturing indexes
            models.Index(fields=['manufacturing_date', 'manufacturing_location', 'is_deleted']),
            models.Index(fields=['batch_number', 'manufacturing_date', 'is_deleted']),

            # Cost analysis indexes
            models.Index(fields=['manufacturing_cost', 'is_deleted']),
        ]


class DigitalProduct(Product):
    """
    Digital product delivered via download
    """
    download_file = models.FileField(
        upload_to='digital_products/',
        null=True, blank=True,
        verbose_name=_("Download File"),
        help_text=_("Digital file for customer download")
    )
    download_limit = models.IntegerField(
        default=1,
        verbose_name=_("Download Limit"),
        help_text=_("Number of times the file can be downloaded")
    )
    access_duration = models.DurationField(
        null=True, blank=True,
        verbose_name=_("Access Duration"),
        help_text=_("How long customers have access (e.g., 30 days)")
    )
    file_size = models.BigIntegerField(
        null=True, blank=True,
        verbose_name=_("File Size"),
        help_text=_("File size in bytes")
    )
    file_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("File Type"),
        help_text=_("File format type (e.g., PDF, MP4, ZIP)")
    )

    def _can_calculate_cost_price(self) -> bool:
        """
        Check if we have enough data to estimate cost price for digital product.
        Overrides the base class method.
        """
        # Digital products might have development costs or platform fees
        # For now, return False as we don't have specific cost fields
        return False

    def _calculate_estimated_cost_price(self) -> Decimal:
        """
        Calculate estimated cost price for digital product.
        Overrides the base class method.
        """
        # Digital products: development_cost / expected_sales + platform_fees
        # For now, return 0 as we don't have specific cost fields
        return Decimal('0.0')

    def get_delivery_info(self):
        """Get delivery information for digital product"""
        return {
            'product_id': self.uuid,
            'product_name': self.product_name,
            'product_type': self.get_product_type_display(),
            'price': float(self.price),
            'stock_status': self.get_stock_status_display(),
            'available_variants': self.get_available_variants_info(),
            'price_range': self.get_variant_price_range(),
            'delivery_type': 'download',
            'file_size': self.file_size,
            'file_type': self.file_type,
            'download_limit': self.download_limit,
            'access_duration_days': self.access_duration.days if self.access_duration else None,
            'instant_delivery': True,
        }

    def validate_purchase(self, quantity=1, color=None, size=None):
        """
        Validate if this digital product can be purchased.
        Overrides the base class method.
        """
        # Digital products typically don't have quantity limits for the product itself
        # But we still need to validate variants if they exist
        if self.has_variants():
            if color or size:
                try:
                    variant = self.variants.get(
                        color=color,
                        size=size,
                        is_deleted=False
                    )
                    if variant.stock_quantity < quantity:
                        raise ValidationError(
                            _("Insufficient stock for selected variant. Only %(stock)s available.") %
                            {'stock': variant.stock_quantity}
                        )
                except ProductVariant.DoesNotExist:
                    raise ValidationError(_("Selected variant is not available"))
            else:
                raise ValidationError(_("Please select a variant for this product"))

        # Digital products don't have traditional stock limits for the base product
        return True

    # For digital products, stock is often unlimited
    def save(self, *args, **kwargs):
        if not self.track_inventory:
            self.stock_quantity = 999999  # Practical "unlimited"
            self.stock_status = StockStatus.IN_STOCK
        super().save(*args, **kwargs)

    class Meta(Product.Meta):
        db_table = "digital_products"
        verbose_name = _("Digital Product")
        verbose_name_plural = _("Digital Products")
        indexes = Product.Meta.indexes + [
            # File properties indexes
            models.Index(fields=['file_type', 'is_deleted']),
            models.Index(fields=['file_size', 'is_deleted']),
            models.Index(fields=['download_limit', 'is_deleted']),
            models.Index(fields=['access_duration', 'is_deleted']),

            # Digital delivery indexes
            models.Index(fields=['file_type', 'file_size', 'is_deleted']),
            models.Index(fields=['download_limit', 'access_duration', 'is_deleted']),

            # Content management indexes
            models.Index(fields=['file_type', 'status', 'is_deleted']),
            models.Index(fields=['file_size', 'file_type', 'is_deleted']),

            # License & access management
            models.Index(fields=['download_limit', 'status', 'is_deleted']),
            models.Index(fields=['access_duration', 'status', 'is_deleted']),
        ]


class ServiceProduct(Product):
    """
    Service-based product (consulting, repairs, etc.)
    """
    duration = models.DurationField(
        verbose_name=_("Service Duration"),
        help_text=_("Expected service duration")
    )
    location_required = models.BooleanField(
        default=False,
        verbose_name=_("Location Required"),
        help_text=_("Whether the service requires physical location access")
    )
    service_type = models.CharField(
        max_length=50,
        choices=ServiceType.choices,
        default=ServiceType.CONSULTATION,
        verbose_name=_("Service Type"),
        help_text=_("Type of service being offered")
    )
    provider_notes = models.TextField(
        blank=True,
        verbose_name=_("Provider Notes"),
        help_text=_("Internal notes for service providers")
    )

    def _can_calculate_cost_price(self) -> bool:
        """
        Check if we have enough data to estimate cost price for service.
        Overrides the base class method.
        """
        # Services might have provider costs or material costs
        # For now, return False as we don't have specific cost fields
        return False

    def _calculate_estimated_cost_price(self) -> Decimal:
        """
        Calculate estimated cost price for service product.
        Overrides the base class method.
        """
        # Services: hourly_rate * estimated_hours + materials
        # For now, return 0 as we don't have specific cost fields
        return Decimal('0.0')

    def get_delivery_info(self):
        """Get delivery information for service product"""
        return {
            'product_id': self.uuid,
            'product_name': self.product_name,
            'product_type': self.get_product_type_display(),
            'price': float(self.price),
            'stock_status': self.get_stock_status_display(),
            'available_variants': self.get_available_variants_info(),
            'price_range': self.get_variant_price_range(),
            'delivery_type': 'service',
            'duration_hours': self.duration.total_seconds() / 3600 if self.duration else None,
            'location_required': self.location_required,
            'service_type': self.service_type,
            'service_category': self.get_service_type_display(),
        }

    def validate_purchase(self, quantity=1, color=None, size=None):
        """
        Validate if this service product can be purchased.
        Overrides the base class method.
        """
        # Services might have capacity limits or scheduling constraints
        # For now, we'll just validate variants if they exist
        if self.has_variants():
            if color or size:
                try:
                    variant = self.variants.get(
                        color=color,
                        size=size,
                        is_deleted=False
                    )
                    if variant.stock_quantity < quantity:
                        raise ValidationError(
                            _("Insufficient capacity for selected service variant. Only %(stock)s available.") %
                            {'stock': variant.stock_quantity}
                        )
                except ProductVariant.DoesNotExist:
                    raise ValidationError(_("Selected service variant is not available"))
            else:
                raise ValidationError(_("Please select a variant for this service"))

        # Services might have additional validation logic here
        # For example: check provider availability, scheduling conflicts, etc.
        return True

    class Meta(Product.Meta):
        db_table = "service_products"
        verbose_name = _("Service")
        verbose_name_plural = _("Services")
        ordering = ["service_type"]
        indexes = Product.Meta.indexes + [
            # Service type indexes
            models.Index(fields=['service_type', 'is_deleted']),
            models.Index(fields=['duration', 'is_deleted']),
            models.Index(fields=['location_required', 'is_deleted']),

            # Service delivery indexes
            models.Index(fields=['service_type', 'duration', 'is_deleted']),
            models.Index(fields=['service_type', 'location_required', 'is_deleted']),
            models.Index(fields=['duration', 'location_required', 'is_deleted']),

            # Service scheduling & availability
            models.Index(fields=['service_type', 'status', 'is_deleted']),
            models.Index(fields=['duration', 'status', 'is_deleted']),
            models.Index(fields=['location_required', 'status', 'is_deleted']),
        ]