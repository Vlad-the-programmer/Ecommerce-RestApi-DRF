import logging
from datetime import timezone, timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Avg
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel, SlugFieldCommonModel
from orders.models import OrderItem
from products.enums import (ProductCondition, ProductStatus,
                            StockStatus, ProductLabel,
                            ServiceType, ProductType)
from products.managers import (ProductManager, ProductReportManager,
                               ProductAdminManager, ProductVariantManager)
from common.models import AddressBaseModel
from reviews.utils import get_stars_for_rating


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


class ProductVariant(CommonModel):
    """
    Product variants with stock management and cost tracking
    """
    objects = ProductVariantManager()

    product = models.ForeignKey(
        "Product",
        on_delete=models.CASCADE,
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

    class Meta:
        db_table = "product_images"
        verbose_name = _("Product Image")
        verbose_name_plural = _("Product Images")
        ordering = ["display_order", "-date_created"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=['product', 'is_deleted']),
            models.Index(fields=['product', 'display_order', 'is_deleted']),
        ]


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
        on_delete=models.CASCADE,
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
        verbose_name=_("Compare At Price")
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
        "Location", on_delete=models.SET_NULL, null=True, blank=True,
        related_name='service_products'
    )
    service_type = models.CharField(
        max_length=50, choices=ServiceType.choices, default=ServiceType.CONSULTATION
    )
    provider_notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        # Auto-update stock_status based on variants
        if self.track_inventory and self.has_variants:
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

    @property
    def total_stock_quantity(self):
        """Aggregate stock from all variants"""
        return self.product_variants.filter(
            is_deleted=False, is_active=True
        ).aggregate(total=models.Sum('stock_quantity'))['total'] or 0

    @property
    def has_variants(self):
        """Check if product has any active variants"""
        return self.product_variants.filter(is_deleted=False, is_active=True).exists()

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

    class Meta:
        db_table = 'products'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        indexes = [
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