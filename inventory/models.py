import datetime
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings

from common.models import CommonModel, AddressBaseModel
from inventory.enums import WAREHOUSE_TYPE
from inventory.managers import InventoryManager, WarehouseManager
from shipping.models import ShippingClass

logger = logging.getLogger(__name__)


class WarehouseProfile(AddressBaseModel):
    """Warehouse model for storing warehouse information"""

    name = models.CharField(max_length=255, db_index=True, help_text=_("Warehouse name"))
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text=_("Warehouse code"))
    contact_phone = models.CharField(max_length=20, blank=True, null=True, help_text=_("Conatct phone of a warehouse"))
    contact_email = models.EmailField(blank=True, null=True, help_text=_("Conatct email of a warehouse"))
    is_operational = models.BooleanField(default=True, db_index=True, help_text=_("Is warehouse operational"))
    capacity = models.PositiveIntegerField(help_text=_("Total storage capacity in units"))

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

    current_utilization = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=0.0,
        db_index=True,
        help_text=_("Current capacity utilization percentage")
    )

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

    tax_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    currency = models.CharField(max_length=3, default='USD', db_index=True)

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
        if not super().is_valid():
            return False

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

        if not (self.contact_phone or self.contact_email):
            logger.warning(f"Warehouse {self.id} must have at least one contact method (phone or email)")
            return False

        if not isinstance(self.capacity, (int, float, Decimal)) or self.capacity <= 0:
            logger.warning(f"Warehouse {self.id} has invalid capacity: {self.capacity}")
            return False

        if not (0 <= self.current_utilization <= 100):
            logger.warning(
                f"Warehouse {self.id} has invalid utilization: {self.current_utilization}% "
                "(must be between 0 and 100)"
            )
            return False

        if not isinstance(self.sla_days, int) or self.sla_days <= 0:
            logger.warning(f"Warehouse {self.id} has invalid SLA days: {self.sla_days}")
            return False

        if not isinstance(self.max_order_per_day, int) or self.max_order_per_day <= 0:
            logger.warning(f"Warehouse {self.id} has invalid max orders per day: {self.max_order_per_day}")
            return False

        try:
            import pytz
            pytz.timezone(self.timezone)
        except (pytz.UnknownTimeZoneError, AttributeError):
            logger.warning(f"Warehouse {self.id} has invalid timezone: {self.timezone}")
            return False

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
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return can_delete, reason

        if self.is_operational:
            message = "Cannot delete an operational warehouse"
            logger.warning(f"{message} (Warehouse ID: {self.id})")
            return False, message

        if hasattr(self, 'inventory_items') and self.inventory_items.filter(
                quantity_available__gt=0
        ).exists():
            item_count = self.inventory_items.filter(quantity_available__gt=0).count()
            message = f"Cannot delete warehouse with {item_count} inventory items in stock"
            logger.warning(f"{message} (Warehouse ID: {self.id})")
            return False, message

        from orders.enums import active_order_statuses
        if hasattr(self, 'orders') and self.orders.filter(
                status__in=active_order_statuses
        ).exists():
            order_count = self.orders.filter(
                status__in=active_order_statuses
            ).count()
            message = f"Cannot delete warehouse with {order_count} active or pending orders"
            logger.warning(f"{message} (Warehouse ID: {self.id})")
            return False, message

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

    last_restocked = models.DateTimeField(null=True, blank=True, db_index=True,
                                           help_text=_("Last restocked date and time"))
    last_checked = models.DateTimeField(auto_now=True, help_text=_("Last checked date and time"))
    is_backorder_allowed = models.BooleanField(default=False, db_index=True,
                                               help_text=_("Allow backorders for this inventory"))

    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True, db_index=True,
        help_text=_("Cost price at this warehouse (can vary by location)")
    )
    batch_number = models.CharField(max_length=100, blank=True, null=True, db_index=True,
                                    help_text=_("Batch number of this inventory"))
    expiry_date = models.DateField(null=True, blank=True, db_index=True, help_text=_("Expiry date of this inventory"))
    last_cost_update = models.DateTimeField(null=True, blank=True, db_index=True,
                                            help_text=_("Last cost update date and time"))
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
        if not super().is_valid():
            return False

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

        if not hasattr(self, 'warehouse') or not self.warehouse:
            logger.warning(f"Inventory {self.id} has no associated warehouse")
            return False

        if not self.warehouse.is_valid():
            logger.warning(f"Inventory {self.id} has invalid warehouse {self.warehouse_id}")
            return False

        if not hasattr(self, 'product_variant') or not self.product_variant:
            logger.warning(f"Inventory {self.id} has no associated product variant")
            return False

        if not self.product_variant.is_valid():
            logger.warning(f"Inventory {self.id} has invalid product variant {self.product_variant_id}")
            return False

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

        if not isinstance(self.reorder_level, (int, float, Decimal)) or self.reorder_level < 0:
            logger.warning(f"Inventory {self.id} has invalid reorder level: {self.reorder_level}")
            return False

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

        if self.expiry_date and not isinstance(self.expiry_date, datetime.date):
            logger.warning(f"Inventory {self.id} has invalid expiry date: {self.expiry_date}")
            return False

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
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            logger.warning(f"Cannot delete inventory {self.id}: {reason}")
            return False, reason

        from orders.enums import active_order_statuses
        if hasattr(self, 'order_items') and self.order_items.filter(
                order__status__in=active_order_statuses,
                order__is_deleted=False
        ).exists():
            active_orders = self.order_items.filter(
                order__status__in=active_order_statuses,
                order__is_deleted=False
            ).values_list('order__id', flat=True).distinct().count()
            message = f"Cannot delete inventory with {active_orders} active orders"
            logger.warning(f"{message} (Inventory ID: {self.id})")
            return False, message

        from orders.enums import active_order_statuses
        active_shippings_with_active_orders = ShippingClass.objects.filter(
                orders__status__in=active_order_statuses,
                orders__is_active=True,
        )
        if active_shippings_with_active_orders.exists():
            for shipping in active_shippings_with_active_orders:
                if shipping.orders.filter(
                        order_items__product__product_variants__in=[self.product_variant],
                        status__in=active_order_statuses
                ).exists():

                    message = f"Cannot delete inventory with active shippings and orders."
                    logger.warning(f"{message} (Inventory ID: {self.id})")
                    return False, message

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

        if self.expiry_date and self.expiry_date < timezone.now().date() and self.quantity_available > 0:
            raise ValidationError(_("Expired items cannot have positive stock quantity"))

    def save(self, *args, **kwargs):
        """Auto-update last_checked on save"""
        self.last_checked = timezone.now()
        kwargs['update_fields'] = ['last_checked', 'date_updated']
        super().save(*args, **kwargs)


class StockMovement(CommonModel):
    """
    Tracks all inventory movements (inbound, outbound, adjustments).
    """

    class MovementType(models.TextChoices):
        PURCHASE = 'purchase', _('Purchase')
        SALE = 'sale', _('Sale')
        RETURN = 'return', _('Return')
        ADJUSTMENT = 'adjustment', _('Adjustment')
        TRANSFER_IN = 'transfer_in', _('Transfer In')
        TRANSFER_OUT = 'transfer_out', _('Transfer Out')
        LOSS = 'loss', _('Loss/Theft')
        DAMAGED = 'damaged', _('Damaged')
        EXPIRE = 'expire', _('Expired')
        COUNT = 'count', _('Stock Count')

    inventory = models.ForeignKey(
        'inventory.Inventory',
        on_delete=models.PROTECT,
        related_name='stock_movements',
        help_text=_('Related inventory item')
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
        db_index=True,
        help_text=_('Type of stock movement')
    )
    quantity = models.IntegerField(
        help_text=_('Positive for additions, negative for subtractions')
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text=_('Reference number/ID from source system (e.g., order number)')
    )
    source_warehouse = models.ForeignKey(
        'inventory.WarehouseProfile',
        on_delete=models.PROTECT,
        related_name='outgoing_movements',
        null=True,
        blank=True,
        help_text=_('Source warehouse for transfers')
    )
    destination_warehouse = models.ForeignKey(
        'inventory.WarehouseProfile',
        on_delete=models.PROTECT,
        related_name='incoming_movements',
        null=True,
        blank=True,
        help_text=_('Destination warehouse for transfers')
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text=_('Additional notes about this movement')
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Unit cost at time of movement')
    )
    total_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Total value of this movement (quantity × unit cost)')
    )
    movement_date = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text=_('When this movement actually occurred')
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_('User who processed this movement')
    )

    class Meta:
        db_table = 'inventory_stock_movements'
        verbose_name = _('Stock Movement')
        verbose_name_plural = _('Stock Movements')
        ordering = ['-movement_date', '-date_created']
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=['inventory', 'movement_date']),
            models.Index(fields=['movement_type', 'movement_date']),
            models.Index(fields=['reference']),
            models.Index(fields=['movement_date', 'movement_type']),
            models.Index(fields=['inventory', 'movement_type', 'movement_date']),
            models.Index(fields=['source_warehouse', 'movement_date']),
            models.Index(fields=['destination_warehouse', 'movement_date']),
            models.Index(fields=['total_value', 'movement_date']),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(source_warehouse=models.F('destination_warehouse')),
                name='different_source_destination'
            ),
            models.CheckConstraint(
                check=~(
                    (models.Q(movement_type__in=['transfer_in', 'transfer_out']) &
                     models.Q(source_warehouse__isnull=True) &
                     models.Q(destination_warehouse__isnull=True))
                ),
                name='transfer_requires_warehouse'
            ),
            models.CheckConstraint(
                check=~(
                        (models.Q(movement_type='transfer_in') & models.Q(destination_warehouse__isnull=True)) |
                        (models.Q(movement_type='transfer_out') & models.Q(source_warehouse__isnull=True))
                ),
                name='valid_transfer_warehouses'
            ),
            models.CheckConstraint(
                check=~(
                        models.Q(quantity=0) |
                        (models.Q(movement_type__in=['purchase', 'return', 'transfer_in']) & models.Q(quantity__lt=0)) |
                        (models.Q(movement_type__in=['sale', 'loss', 'damaged', 'expire', 'transfer_out']) &
                         models.Q(quantity__gt=0))
                ),
                name='valid_quantity_for_movement_type'
            )
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.quantity} units of {self.inventory}"

    def is_valid(self, *args, **kwargs) -> bool:
        """
        Validate the stock movement.

        Returns:
            bool: True if the movement is valid, False otherwise
        """
        if not super().is_valid(*args, **kwargs):
            return False

        if self.movement_type in ['transfer_in', 'transfer_out']:
            if not self.source_warehouse and not self.destination_warehouse:
                logger.warning(
                    f"StockMovement {self.id} is missing both source and destination warehouse"
                )
                return False

        if self.quantity == 0:
            logger.warning(f"StockMovement {self.id} has zero quantity")
            return False

        if not hasattr(self, 'inventory') or not self.inventory:
            logger.warning(f"StockMovement {self.id} is missing inventory item")
            return False

        if not self.inventory.is_valid():
            logger.warning(
                f"StockMovement {self.id} has invalid inventory item {self.inventory_id}"
            )
            return False

        if self.quantity < 0 and not self._has_sufficient_stock():
            logger.warning(
                f"StockMovement {self.id} would result in negative stock for {self.inventory_id}"
            )
            return False

        logger.debug(f"StockMovement {self.id} validation successful")
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the stock movement can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return can_delete, reason

        if self.quantity > 0:
            current_stock = self.inventory.quantity_available
            if current_stock < self.quantity:
                message = (
                    f"Cannot delete this {self.get_movement_type_display()} movement "
                    f"as it would make inventory negative for {self.inventory}"
                )
                logger.warning(f"{message} (Movement ID: {self.id})")
                return False, message

        if self.reference and self.movement_type in ['transfer_in', 'transfer_out']:
            from orders.enums import active_order_statuses
            from orders.models import Order
            if Order.objects.filter(
                    order_number=self.reference,
                    status__in=active_order_statuses
            ).exists():
                message = (
                    f"Cannot delete movement for active transfer {self.reference}"
                )
                logger.warning(f"{message} (Movement ID: {self.id})")
                return False, message

        return True, ""

    def _has_sufficient_stock(self) -> bool:
        """Check if there's enough stock for outbound movement."""
        if self.quantity >= 0:
            return True

        current_stock = self.inventory.quantity_available
        return current_stock >= abs(self.quantity)

    def save(self, *args, **kwargs):
        """Save the stock movement and update inventory."""
        if self.unit_cost is not None:
            self.total_value = abs(self.quantity) * self.unit_cost

        if not self.movement_date:
            self.movement_date = timezone.now()

        if self.movement_type == 'transfer_in' and not self.destination_warehouse:
            self.destination_warehouse = self.inventory.warehouse
        elif self.movement_type == 'transfer_out' and not self.source_warehouse:
            self.source_warehouse = self.inventory.warehouse

            super().save(*args, **kwargs)

            if not self.pk:
                self.inventory.quantity_available = F('quantity_available') + self.quantity
                self.inventory.save(update_fields=['quantity_available', 'date_updated'])
