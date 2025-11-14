import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from common.models import CommonModel, AddressBaseModel
from inventory.enums import WAREHOUSE_TYPE
from inventory.managers import InventoryManager, WarehouseManager
from shipping.models import ShippingClass


class WarehouseProfile(AddressBaseModel):
    """Warehouse model for storing warehouse information"""

    name = models.CharField(max_length=255, db_index=True, help_text=_("Warehouse name"))
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text=_("Warehouse code"))
    contact_phone = models.CharField(max_length=20, blank=True, null=True, help_text=_("Conatct phone of a warehouse"))
    contact_email = models.EmailField(blank=True, null=True, help_text=_("Conatct email of a warehouse"))
    is_operational = models.BooleanField(default=True, db_index=True, help_text=_("Is warehouse operational"))
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
                check=~models.Q(warehouse_type=WAREHOUSE_TYPE.MAIN) | models.Q(is_operational=True),
                name='main_warehouse_must_be_operational',
                condition=models.Q(warehouse_type=WAREHOUSE_TYPE.MAIN)
            ),
        ]
        ordering = ['country', 'state', 'city', 'name']

    objects = WarehouseManager()

    def is_valid(self) -> bool:
        """
        Check if the warehouse is valid for operations with detailed validation.

        Returns:
            bool: True if warehouse is valid for operations, False otherwise with detailed logging
        """
        import logging
        logger = logging.getLogger(__name__)

        # Basic model validation
        if not super().is_valid():
            logger.warning(f"Warehouse {self.id} failed basic model validation")
            return False

        # Check required fields
        required_fields = {
            'name': bool(self.name and self.name.strip()),
            'code': bool(self.code and self.code.strip()),
            'country': bool(self.country),
            'capacity': self.capacity is not None,
            'warehouse_type': bool(self.warehouse_type)
        }

        missing_fields = [field for field, has_value in required_fields.items() if not has_value]
        if missing_fields:
            logger.warning(f"Warehouse {self.id} is missing required fields: {', '.join(missing_fields)}")
            return False

        # Check at least one contact method is provided
        if not (self.contact_phone or self.contact_email):
            logger.warning(f"Warehouse {self.id} must have at least one contact method (phone or email)")
            return False

        # Check capacity is positive
        if not isinstance(self.capacity, (int, float, Decimal)) or self.capacity <= 0:
            logger.warning(f"Warehouse {self.id} has invalid capacity: {self.capacity}")
            return False

        # Check utilization is valid
        if not (0 <= self.current_utilization <= 100):
            logger.warning(
                f"Warehouse {self.id} has invalid utilization: {self.current_utilization}% "
                "(must be between 0 and 100)"
            )
            return False

        # Check SLA days is positive
        if not isinstance(self.sla_days, int) or self.sla_days <= 0:
            logger.warning(f"Warehouse {self.id} has invalid SLA days: {self.sla_days}")
            return False

        # Check max_order_per_day is positive
        if not isinstance(self.max_order_per_day, int) or self.max_order_per_day <= 0:
            logger.warning(f"Warehouse {self.id} has invalid max orders per day: {self.max_order_per_day}")
            return False

        # Check timezone is valid
        try:
            import pytz
            pytz.timezone(self.timezone)
        except (pytz.UnknownTimeZoneError, AttributeError):
            logger.warning(f"Warehouse {self.id} has invalid timezone: {self.timezone}")
            return False

        # Check operational status constraints
        if not self.is_operational and self.is_active_fulfillment:
            logger.warning(
                f"Warehouse {self.id} cannot be set for fulfillment when not operational"
            )
            return False

        if not self.is_operational and self.manager_id:
            logger.warning(
                f"Warehouse {self.id} cannot have a manager when not operational"
            )
            return False

        # Check main warehouse constraints
        if self.warehouse_type == WAREHOUSE_TYPE.MAIN and not self.is_operational:
            logger.warning(
                f"Warehouse {self.id} is a main warehouse and must be operational"
            )
            return False

        logger.debug(f"Warehouse {self.id} validation successful")
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if warehouse can be safely soft-deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        import logging
        logger = logging.getLogger(__name__)

        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            logger.warning(f"Warehouse {self.id} cannot be deleted: {reason}")
            return can_delete, reason

        # Check if warehouse is operational
        if self.is_operational:
            message = "Cannot delete an operational warehouse"
            logger.warning(f"{message} (Warehouse ID: {self.id})")
            return False, message

        # Check for active inventory
        if hasattr(self, 'inventory_items') and self.inventory_items.filter(
                quantity_available__gt=0
        ).exists():
            item_count = self.inventory_items.filter(quantity_available__gt=0).count()
            message = f"Cannot delete warehouse with {item_count} inventory items in stock"
            logger.warning(f"{message} (Warehouse ID: {self.id})")
            return False, message

        from orders.enums import active_order_statuses
        # Check for pending orders
        if hasattr(self, 'orders') and self.orders.filter(
                status__in=active_order_statuses
        ).exists():
            order_count = self.orders.filter(
                status__in=active_order_statuses
            ).count()
            message = f"Cannot delete warehouse with {order_count} active or pending orders"
            logger.warning(f"{message} (Warehouse ID: {self.id})")
            return False, message

        # Check for active transfers
        if self.has_active_orders:
            message = f"Cannot delete warehouse with active orders"
            logger.warning(f"{message} (Warehouse ID: {self.id})")
            return False, message
        return True, ""

    def clean(self):
        """Additional validation"""
        super().clean()

        # Validate utilization doesn't exceed capacity
        if self.current_utilization > 100:
            raise ValidationError(_("Utilization cannot exceed 100%"))

        # Validate main warehouse uniqueness per country
        if self.warehouse_type == WAREHOUSE_TYPE.MAIN and self.is_operational:
            existing_main = WarehouseProfile.objects.filter(
                country=self.country,
                warehouse_type=WAREHOUSE_TYPE.MAIN,
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

    @property
    def has_active_orders(self):
        if WarehouseProfile.objects.get_active_orders(self.id).exists():
            return True
        return False

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
        on_delete=models.PROTECT,
        related_name='inventory_records'
    )
    warehouse = models.ForeignKey(
        "WarehouseProfile",
        on_delete=models.PROTECT,
        related_name='inventory_items'
    )
    quantity_available = models.PositiveIntegerField(default=0, db_index=True,
                                                     help_text=_("Available quantity in units"))
    quantity_reserved = models.PositiveIntegerField(default=0, db_index=True,
                                                    help_text=_("Reserved quantity in units"))
    reorder_level = models.PositiveIntegerField(default=10, help_text=_("Reorder level in units"))

    # Additional useful fields
    last_restocked = models.DateTimeField(null=True, blank=True, db_index=True,
                                           help_text=_("Last restocked date and time"))
    last_checked = models.DateTimeField(auto_now=True, help_text=_("Last checked date and time"))
    is_backorder_allowed = models.BooleanField(default=False, db_index=True,
                                               help_text=_("Allow backorders for this inventory"))

    # Add for better inventory management
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True, db_index=True,
        help_text=_("Cost price at this warehouse (can vary by location)")
    )
    batch_number = models.CharField(max_length=100, blank=True, null=True, db_index=True,
                                    help_text=_("Batch number of this inventory"))
    expiry_date = models.DateField(null=True, blank=True, db_index=True, help_text=_("Expiry date of this inventory"))

    # Add for inventory valuation
    last_cost_update = models.DateTimeField(null=True, blank=True, db_index=True,
                                            help_text=_("Last cost update date and time"))

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

    objects = InventoryManager()

    def is_valid(self) -> bool:
        """Check if inventory is valid for order fulfillment with detailed validation.

        Returns:
            bool: True if inventory is valid for fulfillment, False otherwise with detailed logging
        """
        import logging
        logger = logging.getLogger(__name__)

        # Basic model validation
        if not super().is_valid():
            logger.warning(f"Inventory {self.id} failed basic model validation")
            return False

        # Check required fields
        required_fields = {
            'product_variant_id': bool(self.product_variant_id),
            'warehouse_id': bool(self.warehouse_id),
            'quantity_available': self.quantity_available is not None,
            'quantity_reserved': self.quantity_reserved is not None,
            'reorder_level': self.reorder_level is not None
        }
        missing_fields = [field for field, has_value in required_fields.items() if not has_value]
        if missing_fields:
            logger.warning(f"Inventory {self.id} is missing required fields: {', '.join(missing_fields)}")
            return False

        # Check warehouse validity
        if not hasattr(self, 'warehouse') or not self.warehouse:
            logger.warning(f"Inventory {self.id} has no associated warehouse")
            return False

        if not self.warehouse.is_valid():
            logger.warning(f"Inventory {self.id} has invalid warehouse {self.warehouse_id}")
            return False

        # Check product variant validity
        if not hasattr(self, 'product_variant') or not self.product_variant:
            logger.warning(f"Inventory {self.id} has no associated product variant")
            return False

        if not self.product_variant.is_valid():
            logger.warning(f"Inventory {self.id} has invalid product variant {self.product_variant_id}")
            return False

        # Check quantity constraints
        if not isinstance(self.quantity_available, (int, float, Decimal)) or self.quantity_available < 0:
            logger.warning(f"Inventory {self.id} has invalid available quantity: {self.quantity_available}")
            return False

        if not isinstance(self.quantity_reserved, (int, float, Decimal)) or self.quantity_reserved < 0:
            logger.warning(f"Inventory {self.id} has invalid reserved quantity: {self.quantity_reserved}")
            return False

        if self.quantity_reserved > self.quantity_available:
            logger.warning(
                f"Inventory {self.id} has reserved quantity ({self.quantity_reserved}) "
                f"greater than available quantity ({self.quantity_available})"
            )
            return False

        # Check reorder level
        if not isinstance(self.reorder_level, (int, float, Decimal)) or self.reorder_level < 0:
            logger.warning(f"Inventory {self.id} has invalid reorder level: {self.reorder_level}")
            return False

        # Check cost-related fields
        cost_fields = {
            'cost_price': self.cost_price,
            'manufacturing_cost_adjustment': self.manufacturing_cost_adjustment,
            'packaging_cost_adjustment': self.packaging_cost_adjustment,
            'shipping_cost_adjustment': self.shipping_cost_adjustment
        }
        for field, value in cost_fields.items():
            if value is not None and (not isinstance(value, (int, float, Decimal)) or value < 0):
                logger.warning(f"Inventory {self.id} has invalid {field}: {value}")
                return False

        # Check expiry date
        if self.expiry_date and not isinstance(self.expiry_date, datetime.date):
            logger.warning(f"Inventory {self.id} has invalid expiry date: {self.expiry_date}")
            return False

        # Check if inventory is expired
        if self.is_expired:
            logger.warning(f"Inventory {self.id} has expired on {self.expiry_date}")
            return False

        logger.debug(f"Inventory {self.id} validation successful")
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """Check if inventory can be safely soft-deleted with detailed validation.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        import logging
        logger = logging.getLogger(__name__)

        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            logger.warning(f"Cannot delete inventory {self.id}: {reason}")
            return False, reason

        from orders.enums import active_order_statuses
        # Check if there are any active orders for this inventory
        if hasattr(self, 'order_items') and self.order_items.filter(
                order__status__in=active_order_statuses,
                order__is_deleted=False,
                is_deleted=False
        ).exists():
            active_orders = self.order_items.filter(
                order__status__in=active_order_statuses,
                order__is_deleted=False
            ).values_list('order__id', flat=True).distinct().count()
            message = f"Cannot delete inventory with {active_orders} active orders"
            logger.warning(f"{message} (Inventory ID: {self.id})")
            return False, message

        from orders.enums import active_order_statuses
        # Check if there are any pending shippings with this inventory
        active_shippings_with_active_orders = ShippingClass.objects.filter(
                orders__status__in=active_order_statuses,
                orders__is_active=True,
                is_active=False,
        )
        if active_shippings_with_active_orders.exists():
            for shipping in active_shippings_with_active_orders:
                # If there are any active shippings with active orders which contain the inventory product
                if shipping.orders.filter(
                        order_items__product__product_variants__in=[self.product_variant],
                        status__in=active_order_statuses,
                        is_active=True,
                        is_deleted=False
                ).exists():

                    message = f"Cannot delete inventory with active shippings and orders."
                    logger.warning(f"{message} (Inventory ID: {self.id})")
                    return False, message

        # Check if warehouse is operational (inverse logic - we can delete if warehouse is NOT operational)
        if self.warehouse and self.warehouse.is_operational:
            message = "Cannot delete inventory from operational warehouse"
            logger.warning(f"{message} (Inventory ID: {self.id}, Warehouse ID: {self.warehouse_id})")
            return False, message

        logger.info(f"Inventory {self.id} can be safely deleted")
        return True, ""

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

        if self.warehouse.is_deleted:
            raise ValidationError(_("Cannot assign inventory to deleted warehouse"))

        if self.product_variant.is_deleted:
            raise ValidationError(_("Cannot assign inventory to deleted product variant"))

        # Validate expiry date is not in the past for items with stock
        if self.expiry_date and self.expiry_date < timezone.now().date() and self.quantity_available > 0:
            raise ValidationError(_("Expired items cannot have positive stock quantity"))

    def save(self, *args, **kwargs):
        """Auto-update last_checked on save"""
        self.last_checked = timezone.now()
        super().save(*args, **kwargs)
