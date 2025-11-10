from datetime import timedelta

from django.utils import timezone
from django.db.models import Count, Sum, F, Q
from common.managers import SoftDeleteManager


class WarehouseManager(SoftDeleteManager):
    """
    Custom manager for WarehouseProfile with warehouse-specific methods.
    """

    def operational(self):
        """Get all operational warehouses"""
        return self.get_queryset().filter(is_operational=True)

    def available_for_fulfillment(self):
        """Get warehouses available for order fulfillment"""
        return self.get_queryset().filter(
            is_operational=True,
            is_active_fulfillment=True
        )

    def by_country(self, country_code):
        """Get warehouses by country"""
        return self.get_queryset().filter(country=country_code)

    def by_type(self, warehouse_type):
        """Get warehouses by type"""
        return self.get_queryset().filter(warehouse_type=warehouse_type)

    def with_capacity(self, min_available_percent=10):
        """Get warehouses with available capacity"""
        return self.get_queryset().filter(
            current_utilization__lte=(100 - min_available_percent)
        )

    def near_capacity(self, threshold=90):
        """Get warehouses near capacity"""
        return self.get_queryset().filter(
            current_utilization__gte=threshold
        )

    def with_express_shipping(self):
        """Get warehouses with express shipping available"""
        return self.get_queryset().filter(is_express_available=True)

    def get_main_warehouses(self):
        """Get all main warehouses"""
        return self.get_queryset().filter(warehouse_type='main')

    def get_by_manager(self, user_id):
        """Get warehouses managed by specific user"""
        return self.get_queryset().filter(manager_id=user_id)

    def with_inventory_stats(self):
        """Annotate warehouses with inventory statistics"""
        return self.get_queryset().annotate(
            total_products=Count('inventory_items', distinct=True),
            total_quantity=Sum('inventory_items__quantity_available'),
            total_value=Sum(
                F('inventory_items__quantity_available') *
                F('inventory_items__cost_price')
            )
        )

    def get_optimal_warehouse(self, country=None, state=None, product_variant_ids=None):
        """
        Find optimal warehouse based on location, capacity, and product availability.
        """
        queryset = self.available_for_fulfillment()

        # Filter by location if provided
        if country:
            queryset = queryset.filter(country=country)
        if state:
            queryset = queryset.filter(state=state)

        # Further filter by product availability if product IDs provided
        if product_variant_ids:
            from django.db.models import Exists, OuterRef
            from inventory.models import Inventory

            # Check if warehouse has inventory for all required products
            for product_id in product_variant_ids:
                queryset = queryset.filter(
                    inventory_items__product_variant_id=product_id,
                    inventory_items__quantity_available__gt=0
                )

        # Order by best options
        return queryset.order_by(
            'current_utilization',  # Prefer less utilized
            'sla_days',  # Prefer faster SLA
            'is_express_available'  # Prefer express available
        ).first()


class InventoryManager(SoftDeleteManager):
    """
    Custom manager for Inventory with inventory-specific methods.
    """

    def get_warehouse_inventory(self, warehouse_id):
        """Get all inventory for a specific warehouse"""
        return self.get_queryset().filter(warehouse_id=warehouse_id)

    def get_product_inventory(self, product_variant_id):
        """Get all inventory records for a specific product variant"""
        return self.get_queryset().filter(product_variant_id=product_variant_id)

    def get_by_product_and_warehouse(self, product_variant_id, warehouse_id):
        """Get specific inventory record for product in warehouse"""
        return self.get_queryset().filter(
            product_variant_id=product_variant_id,
            warehouse_id=warehouse_id
        ).first()

    def low_stock_items(self, threshold_ratio=1.0):
        """Get items at or below reorder level"""
        return self.get_queryset().filter(
            quantity_available__lte=F('reorder_level') * threshold_ratio
        )

    def out_of_stock_items(self):
        """Get items that are out of stock"""
        return self.get_queryset().filter(quantity_available=0)

    def in_stock_items(self):
        """Get items that are in stock"""
        return self.get_queryset().filter(quantity_available__gt=0)

    def expired_items(self):
        """Get expired inventory items"""
        return self.get_queryset().filter(
            expiry_date__lt=timezone.now().date(),
            quantity_available__gt=0
        )

    def expiring_soon(self, days=30):
        """Get items expiring within specified days"""
        target_date = timezone.now().date() + timedelta(days=days)
        return self.get_queryset().filter(
            expiry_date__lte=target_date,
            expiry_date__gte=timezone.now().date(),
            quantity_available__gt=0
        )

    def with_backorder(self):
        """Get items that allow backorders"""
        return self.get_queryset().filter(is_backorder_allowed=True)

    def by_batch_number(self, batch_number):
        """Get inventory by batch number"""
        return self.get_queryset().filter(batch_number=batch_number)

    def get_total_quantity(self, product_variant_id=None, warehouse_id=None):
        """Get total available quantity with optional filters"""
        queryset = self.get_queryset()

        if product_variant_id:
            queryset = queryset.filter(product_variant_id=product_variant_id)
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)

        return queryset.aggregate(total=Sum('quantity_available'))['total'] or 0

    def get_inventory_value(self, warehouse_id=None):
        """Calculate total inventory value"""
        queryset = self.get_queryset().filter(
            cost_price__isnull=False,
            quantity_available__gt=0
        )

        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)

        return queryset.aggregate(
            total_value=Sum(F('cost_price') * F('quantity_available'))
        )['total_value'] or 0

    def update_batch_cost(self, batch_number, new_cost_price):
        """Update cost price for all items in a batch"""
        return self.get_queryset().filter(batch_number=batch_number).update(
            cost_price=new_cost_price,
            last_cost_update=timezone.now()
        )

    def get_inventory_summary(self, warehouse_id=None):
        """Get comprehensive inventory summary"""
        queryset = self.get_queryset()

        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)

        return queryset.aggregate(
            total_products=Count('product_variant', distinct=True),
            total_quantity=Sum('quantity_available'),
            total_reserved=Sum('quantity_reserved'),
            total_value=Sum(F('cost_price') * F('quantity_available')),
            low_stock_count=Count('id', filter=Q(quantity_available__lte=F('reorder_level'))),
            out_of_stock_count=Count('id', filter=Q(quantity_available=0))
        )