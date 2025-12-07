import django_filters
from django.db.models import Q

from inventory.models import Inventory, WarehouseProfile
from inventory.enums import WAREHOUSE_TYPE


class InventoryFilter(django_filters.FilterSet):
    """
    Filter for Inventory model with support for:
    - Product variant filtering
    - Warehouse filtering
    - Stock status filtering
    - Date range filtering
    - Cost range filtering
    """
    product_variant = django_filters.CharFilter(
        field_name='product_variant__name',
        lookup_expr='icontains',
        label='Product Variant Name',
    )
    
    sku = django_filters.CharFilter(
        field_name='product_variant__sku',
        lookup_expr='iexact',
        label='SKU',
    )
    
    warehouse = django_filters.CharFilter(
        field_name='warehouse__name',
        lookup_expr='icontains',
        label='Warehouse Name',
    )
    
    warehouse_code = django_filters.CharFilter(
        field_name='warehouse__code',
        lookup_expr='iexact',
        label='Warehouse Code',
    )
    
    stock_status = django_filters.ChoiceFilter(
        method='filter_stock_status',
        choices=[
            ('in_stock', 'In Stock'),
            ('out_of_stock', 'Out of Stock'),
            ('low_stock', 'Low Stock'),
        ],
        label='Stock Status',
    )
    
    min_quantity = django_filters.NumberFilter(
        field_name='quantity_available',
        lookup_expr='gte',
        label='Minimum Quantity',
    )
    
    max_quantity = django_filters.NumberFilter(
        field_name='quantity_available',
        lookup_expr='lte',
        label='Maximum Quantity',
    )
    
    min_cost = django_filters.NumberFilter(
        field_name='cost_price',
        lookup_expr='gte',
        label='Minimum Cost',
    )
    
    max_cost = django_filters.NumberFilter(
        field_name='cost_price',
        lookup_expr='lte',
        label='Maximum Cost',
    )
    
    last_restocked_after = django_filters.DateFilter(
        field_name='last_restocked',
        lookup_expr='gte',
        label='Restocked After',
    )
    
    last_restocked_before = django_filters.DateFilter(
        field_name='last_restocked',
        lookup_expr='lte',
        label='Restocked Before',
    )
    
    batch_number = django_filters.CharFilter(
        field_name='batch_number',
        lookup_expr='icontains',
        label='Batch Number',
    )
    
    class Meta:
        model = Inventory
        fields = {
            'is_backorder_allowed': ['exact'],
            'expiry_date': ['lte', 'gte', 'lt', 'gt'],
        }
    
    def filter_stock_status(self, queryset, name, value):
        """
        Filter by stock status:
        - in_stock: Quantity available > 0
        - out_of_stock: Quantity available = 0
        - low_stock: Quantity available <= reorder_level
        """
        if value == 'in_stock':
            return queryset.filter(quantity_available__gt=0)
        elif value == 'out_of_stock':
            return queryset.filter(quantity_available=0)
        elif value == 'low_stock':
            return queryset.filter(quantity_available__lte=django_filters.F('reorder_level'))
        return queryset


class WarehouseFilter(django_filters.FilterSet):
    """
    Filter for Warehouse model with support for:
    - Name and code filtering
    - Location-based filtering
    - Operational status filtering
    - Capacity-based filtering
    """
    name = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Warehouse Name',
    )
    
    code = django_filters.CharFilter(
        field_name='code',
        lookup_expr='iexact',
        label='Warehouse Code',
    )
    
    city = django_filters.CharFilter(
        field_name='city',
        lookup_expr='icontains',
        label='City',
    )
    
    state = django_filters.CharFilter(
        field_name='state',
        lookup_expr='icontains',
        label='State/Province',
    )
    
    country = django_filters.CharFilter(
        field_name='country',
        lookup_expr='iexact',
        label='Country Code',
    )
    
    warehouse_type = django_filters.ChoiceFilter(
        field_name='warehouse_type',
        choices=WAREHOUSE_TYPE.choices,
        label='Warehouse Type',
    )
    
    min_capacity = django_filters.NumberFilter(
        field_name='capacity',
        lookup_expr='gte',
        label='Minimum Capacity',
    )
    
    max_capacity = django_filters.NumberFilter(
        field_name='capacity',
        lookup_expr='lte',
        label='Maximum Capacity',
    )
    
    min_utilization = django_filters.NumberFilter(
        method='filter_min_utilization',
        label='Minimum Utilization %',
    )
    
    max_utilization = django_filters.NumberFilter(
        method='filter_max_utilization',
        label='Maximum Utilization %',
    )
    
    has_express = django_filters.BooleanFilter(
        field_name='is_express_available',
        label='Has Express Shipping',
    )
    
    class Meta:
        model = WarehouseProfile
        fields = {
            'is_operational': ['exact'],
            'is_active_fulfillment': ['exact'],
            'date_created': ['gte', 'lte', 'gt', 'lt'],
            'date_updated': ['gte', 'lte', 'gt', 'lt'],
        }
    
    def filter_min_utilization(self, queryset, name, value):
        """Filter by minimum capacity utilization percentage."""
        return queryset.filter(current_utilization__gte=value)
    
    def filter_max_utilization(self, queryset, name, value):
        """Filter by maximum capacity utilization percentage."""
        return queryset.filter(current_utilization__lte=value)
