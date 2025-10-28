from datetime import timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel, AddressBaseModel
from inventory.enums import WAREHOUSE_TYPE


class WarehouseProfile(AddressBaseModel):
    """Warehouse model for storing warehouse information"""

    name = models.CharField(max_length=255, db_index=True)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    is_operational = models.BooleanField(default=True, db_index=True)
    capacity = models.PositiveIntegerField(help_text=_("Total storage capacity in units"))

    # Additional useful fields for warehouse management
    warehouse_type = models.CharField(
        max_length=20,
        choices=WAREHOUSE_TYPE.choices,
        default=WAREHOUSE_TYPE.REGIONAL,
        db_index=True
    )
    operating_hours = models.JSONField(
        blank=True,
        null=True,
        help_text=_("Structured operating hours (e.g., {'mon': {'open': '09:00', 'close': '18:00'}})")
    )
    manager = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses'
    )

    # Add capacity management
    current_utilization = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=0.0,
        db_index=True,
        help_text=_("Current capacity utilization percentage")
    )

    # Add service metrics
    sla_days = models.PositiveIntegerField(
        default=2,
        db_index=True,
        help_text=_("Standard order processing time in days")
    )
    is_express_available = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Whether express processing is available")
    )

    # Add financial details
    tax_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    currency = models.CharField(max_length=3, default='USD', db_index=True)

    # Additional operational fields
    is_active_fulfillment = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Whether this warehouse is active for order fulfillment")
    )
    max_order_per_day = models.PositiveIntegerField(
        default=1000,
        help_text=_("Maximum orders this warehouse can process per day")
    )
    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text=_("Timezone of the warehouse location")
    )

    class Meta:
        db_table = 'warehouses'
        verbose_name = _("Warehouse")
        verbose_name_plural = _("Warehouses")
        indexes = AddressBaseModel.Meta.indexes + [
            # Warehouse-specific indexes
            models.Index(fields=['country', 'is_operational']),
            models.Index(fields=['state', 'is_operational']),
            models.Index(fields=['city', 'is_operational']),
            models.Index(fields=['is_operational', 'is_active']),
            models.Index(fields=['warehouse_type', 'is_operational']),
            models.Index(fields=['code', 'is_active']),
            models.Index(fields=['name', 'is_operational']),

            # Capacity and utilization
            models.Index(fields=['current_utilization', 'is_operational']),
            models.Index(fields=['capacity', 'current_utilization']),
            models.Index(fields=['warehouse_type', 'current_utilization', 'is_operational']),

            # Service level indexes
            models.Index(fields=['sla_days', 'is_operational']),
            models.Index(fields=['is_express_available', 'is_operational']),
            models.Index(fields=['warehouse_type', 'sla_days', 'is_operational']),

            # Fulfillment operations
            models.Index(fields=['is_active_fulfillment', 'is_operational']),
            models.Index(fields=['warehouse_type', 'is_active_fulfillment', 'is_operational']),
            models.Index(fields=['country', 'is_active_fulfillment', 'is_operational']),

            # Composite indexes for common queries
            models.Index(fields=['country', 'state', 'is_operational']),
            models.Index(fields=['warehouse_type', 'country', 'is_active']),
            models.Index(fields=['country', 'city', 'is_operational']),
            models.Index(fields=['state', 'city', 'is_operational']),
            models.Index(fields=['warehouse_type', 'is_operational', 'is_active_fulfillment']),

            # Manager and operational queries
            models.Index(fields=['manager', 'is_operational']),
            models.Index(fields=['is_operational', 'is_active', 'is_active_fulfillment']),

            # Geographic optimization
            models.Index(fields=['country', 'state', 'city', 'is_operational']),

            # Performance for inventory joins
            models.Index(fields=['id', 'is_operational', 'is_active']),
            models.Index(fields=['code', 'is_operational', 'is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'country'],
                name='unique_warehouse_name_country',
                condition=models.Q(is_deleted=False)
            ),
            models.UniqueConstraint(
                fields=['code'],
                name='unique_warehouse_code',
                condition=models.Q(is_deleted=False)
            ),
            models.CheckConstraint(
                check=models.Q(capacity__gt=0),
                name='warehouse_capacity_positive'
            ),
            models.CheckConstraint(
                check=models.Q(contact_phone__isnull=False) | models.Q(contact_email__isnull=False),
                name='at_least_one_contact_method'
            ),
            models.CheckConstraint(
                check=models.Q(current_utilization__gte=0) & models.Q(current_utilization__lte=100),
                name='valid_utilization_range'
            ),
            models.CheckConstraint(
                check=models.Q(sla_days__gt=0),
                name='positive_sla_days'
            ),
            models.CheckConstraint(
                check=models.Q(max_order_per_day__gt=0),
                name='positive_max_orders'
            ),
            models.CheckConstraint(
                check=(
                        models.Q(is_active_fulfillment=False) |
                        models.Q(is_operational=True)
                ),
                name='fulfillment_requires_operational'
            ),
            models.CheckConstraint(
                check=(
                        models.Q(manager__isnull=True) |
                        models.Q(is_operational=True)
                ),
                name='manager_requires_operational'
            ),
            models.CheckConstraint(
                check=~models.Q(warehouse_type='main') | models.Q(is_operational=True),
                name='main_warehouse_must_be_operational',
                condition=models.Q(warehouse_type='main')
            ),
        ]
        ordering = ['country', 'state', 'city', 'name']

    def clean(self):
        """Additional validation"""
        super().clean()

        # Validate utilization doesn't exceed capacity
        if self.current_utilization > 100:
            raise ValidationError(_("Utilization cannot exceed 100%"))

        # Validate main warehouse uniqueness per country
        if self.warehouse_type == 'main' and self.is_operational:
            existing_main = WarehouseProfile.objects.filter(
                country=self.country,
                warehouse_type='main',
                is_operational=True,
                is_deleted=False
            ).exclude(pk=self.pk)
            if existing_main.exists():
                raise ValidationError(_("Only one main warehouse allowed per country"))

    @property
    def is_available_for_fulfillment(self):
        return self.is_operational and self.is_active_fulfillment

    @property
    def available_capacity(self):
        """Calculate available capacity in units"""
        return self.capacity - (self.capacity * self.current_utilization / 100)

    @property
    def is_at_capacity(self):
        """Check if warehouse is at or near capacity"""
        return self.current_utilization >= 95

    def update_utilization(self, inventory_queryset=None):
        """Update current utilization based on inventory"""
        if inventory_queryset is None:
            inventory_queryset = self.inventory_items.filter(is_deleted=False)

        total_units = inventory_queryset.aggregate(
            total=models.Sum('quantity_available')
        )['total'] or 0

        if self.capacity > 0:
            self.current_utilization = (total_units / self.capacity) * 100
            self.save(update_fields=['current_utilization', 'date_updated'])


class Inventory(CommonModel):
    product_variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.CASCADE,
        related_name='inventory_records'
    )
    warehouse = models.ForeignKey(
        "WarehouseProfile",
        on_delete=models.CASCADE,
        related_name='inventory_items'
    )
    quantity_available = models.PositiveIntegerField(default=0, db_index=True)
    quantity_reserved = models.PositiveIntegerField(default=0, db_index=True)
    reorder_level = models.PositiveIntegerField(default=10)

    # Additional useful fields
    last_restocked = models.DateTimeField(null=True, blank=True, db_index=True)
    last_checked = models.DateTimeField(auto_now=True)
    is_backorder_allowed = models.BooleanField(default=False, db_index=True)

    # Add for better inventory management
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True, db_index=True,
        help_text=_("Cost price at this warehouse (can vary by location)")
    )
    batch_number = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)

    # Add for inventory valuation
    last_cost_update = models.DateTimeField(null=True, blank=True)

    # Additional manufacturing fields for SPECIFIC inventory batches
    manufacturing_cost_adjustment = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text=_("Additional manufacturing cost for this specific batch/location")
    )
    packaging_cost_adjustment = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True, default=0.0,
        help_text=_("Additional packaging cost for this specific batch/location")
    )
    shipping_cost_adjustment = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True, default=0.0,
        help_text=_("Additional shipping cost for this specific batch/location")
    )

    class Meta:
        db_table = 'inventory'
        verbose_name = _("Inventory")
        verbose_name_plural = _("Inventories")
        indexes = CommonModel.Meta.indexes + [
            # Core query patterns
            models.Index(fields=['product_variant', 'warehouse', 'is_deleted']),
            models.Index(fields=['warehouse', 'product_variant', 'is_deleted']),
            models.Index(fields=['product_variant', 'warehouse', 'is_active', 'is_deleted']),

            # Stock level queries
            models.Index(fields=['quantity_available', 'is_active']),
            models.Index(fields=['warehouse', 'quantity_available', 'is_active']),
            models.Index(fields=['product_variant', 'quantity_available', 'is_active']),
            models.Index(fields=['quantity_available', 'quantity_reserved', 'is_active']),

            # Low stock alerts
            models.Index(fields=['quantity_available', 'reorder_level', 'is_active']),
            models.Index(fields=['warehouse', 'quantity_available', 'reorder_level', 'is_active']),
            models.Index(fields=['product_variant', 'quantity_available', 'reorder_level', 'is_active']),

            # Date-based inventory analysis
            models.Index(fields=['last_restocked', 'is_active']),
            models.Index(fields=['warehouse', 'last_restocked', 'is_active']),
            models.Index(fields=['last_restocked', 'quantity_available', 'is_active']),

            # Backorder management
            models.Index(fields=['is_backorder_allowed', 'quantity_available', 'is_active']),
            models.Index(fields=['warehouse', 'is_backorder_allowed', 'is_active']),

            # Expiry management
            models.Index(fields=['expiry_date', 'is_active']),
            models.Index(fields=['warehouse', 'expiry_date', 'is_active']),
            models.Index(fields=['product_variant', 'expiry_date', 'is_active']),
            models.Index(fields=['expiry_date', 'quantity_available', 'is_active']),

            # Batch tracking
            models.Index(fields=['batch_number', 'is_active']),
            models.Index(fields=['warehouse', 'batch_number', 'is_active']),

            # Cost analysis
            models.Index(fields=['cost_price', 'is_active']),
            models.Index(fields=['warehouse', 'cost_price', 'is_active']),

            # Composite indexes for reporting
            models.Index(fields=['warehouse', 'is_active', 'date_created']),
            models.Index(fields=['product_variant', 'is_active', 'date_created']),
            models.Index(fields=['is_active', 'quantity_available', 'date_created']),
            models.Index(fields=['warehouse', 'product_variant', 'date_created', 'is_active']),

            # Performance for common joins
            models.Index(fields=['product_variant', 'is_deleted', 'is_active']),
            models.Index(fields=['warehouse', 'is_deleted', 'is_active']),
            models.Index(fields=['product_variant', 'warehouse', 'is_deleted', 'is_active']),

            # Real-time inventory monitoring
            models.Index(fields=['last_checked', 'is_active']),
            models.Index(fields=['warehouse', 'last_checked', 'is_active']),        ]
        constraints = [
            # ... (keep all your existing constraints) ...
            models.CheckConstraint(
                check=models.Q(manufacturing_cost_adjustment__isnull=True) | models.Q(
                    manufacturing_cost_adjustment__gte=0),
                name='non_negative_mfg_adjustment'
            ),
            models.CheckConstraint(
                check=models.Q(packaging_cost_adjustment__isnull=True) | models.Q(packaging_cost_adjustment__gte=0),
                name='non_negative_packaging_adjustment'
            ),
            models.CheckConstraint(
                check=models.Q(shipping_cost_adjustment__isnull=True) | models.Q(shipping_cost_adjustment__gte=0),
                name='non_negative_shipping_adjustment'
            ),
        ]
        ordering = ['warehouse', 'product_variant']

    @property
    def total_landed_cost(self):
        """Calculate total landed cost including adjustments"""
        base_cost = self.cost_price or Decimal('0.0')
        mfg_adjust = self.manufacturing_cost_adjustment or Decimal('0.0')
        packaging_adjust = self.packaging_cost_adjustment or Decimal('0.0')
        shipping_adjust = self.shipping_cost_adjustment or Decimal('0.0')

        return base_cost + mfg_adjust + packaging_adjust + shipping_adjust

    @property
    def inventory_value(self):
        """Calculate total value of this inventory item"""
        return self.total_landed_cost * self.quantity_available

    @property
    def is_expired(self):
        """Check if this specific inventory batch has expired"""
        if not self.expiry_date:
            return False
        return timezone.now().date() > self.expiry_date

    @property
    def days_until_expiry(self):
        """Get days until this batch expires"""
        if not self.expiry_date:
            return None
        today = timezone.now().date()
        return (self.expiry_date - today).days

    def get_detailed_cost_breakdown(self):
        """Get comprehensive cost breakdown"""
        return {
            'base_cost_price': float(self.cost_price) if self.cost_price else None,
            'manufacturing_cost_adjustment': float(
                self.manufacturing_cost_adjustment) if self.manufacturing_cost_adjustment else None,
            'packaging_cost_adjustment': float(
                self.packaging_cost_adjustment) if self.packaging_cost_adjustment else None,
            'shipping_cost_adjustment': float(self.shipping_cost_adjustment) if self.shipping_cost_adjustment else None,
            'total_landed_cost': float(self.total_landed_cost),
            'total_inventory_value': float(self.inventory_value),
            'batch_number': self.batch_number,
            'expiry_date': self.expiry_date,
            'is_expired': self.is_expired,
            'days_until_expiry': self.days_until_expiry,
        }

    def update_cost_price(self, new_cost, update_timestamp=True):
        """Update cost price with timestamp"""
        self.cost_price = new_cost
        if update_timestamp:
            self.last_cost_update = timezone.now()
        self.save(update_fields=['cost_price', 'last_cost_update', 'date_updated'])

    def clean(self):
        """Additional validation"""
        super().clean()

        # Validate expiry date is not in the past for items with stock
        if self.expiry_date and self.expiry_date < timezone.now().date() and self.quantity_available > 0:
            raise ValidationError(_("Expired items cannot have positive stock quantity"))

    def save(self, *args, **kwargs):
        """Auto-update last_checked on save"""
        self.last_checked = timezone.now()
        super().save(*args, **kwargs)
