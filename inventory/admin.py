from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.safestring import mark_safe

from inventory.models import WarehouseProfile, Inventory, StockMovement
from inventory.filters import InventoryFilter, WarehouseFilter


@admin.register(WarehouseProfile)
class WarehouseProfileAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'code', 'warehouse_type', 'country', 'city', 'is_operational',
        'is_active_fulfillment', 'current_utilization_percent', 'inventory_link'
    )
    list_filter = (
        'warehouse_type', 'is_operational', 'is_active_fulfillment',
        'is_express_available', 'country'
    )
    search_fields = ('name', 'code', 'city', 'state', 'country')
    readonly_fields = ('current_utilization', 'date_created', 'date_updated', 'inventory_preview')
    list_per_page = 25
    filter_horizontal = ()
    ordering = ('name',)
    date_hierarchy = 'date_created'
    filter_class = WarehouseFilter
    list_select_related = True

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'code', 'warehouse_type', 'is_operational', 'is_active_fulfillment')
        }),
        (_('Contact Information'), {
            'fields': ('contact_phone', 'contact_email')
        }),
        (_('Location'), {
            'fields': (
                'address_line_1', 'address_line_2', 'city', 'state',
                'zip_code', 'country', 'timezone'
            )
        }),
        (_('Capacity & Performance'), {
            'fields': (
                'capacity', 'current_utilization', 'max_order_per_day',
                'sla_days', 'is_express_available'
            )
        }),
        (_('Additional Information'), {
            'fields': ('tax_id', 'currency', 'operating_hours', 'manager'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('date_created', 'date_updated'),
            'classes': ('collapse',)
        }),
        (_('Inventory Preview'), {
            'fields': ('inventory_preview',),
            'classes': ('collapse',)
        }),
    )

    def current_utilization_percent(self, obj):
        return f"{obj.current_utilization}%"

    current_utilization_percent.short_description = _('Utilization')
    current_utilization_percent.admin_order_field = 'current_utilization'

    def inventory_link(self, obj):
        url = (
                reverse('admin:inventory_inventory_changelist') +
                f'?warehouse__id__exact={obj.id}'
        )
        count = obj.inventory_items.count()
        return format_html('<a href="{}">{} Items</a>', url, count)

    inventory_link.short_description = _('Inventory Items')

    def inventory_preview(self, obj):
        inventory_items = obj.inventory_items.select_related('product_variant')[:10]
        if not inventory_items:
            return _('No inventory items')

        items = []
        for item in inventory_items:
            items.append(
                f'<li>{item.product_variant} - {item.quantity_available} available</li>'
            )
        return mark_safe(f'<ul>{"".join(items)}</ul>')

    inventory_preview.short_description = _('Top 10 Items')
    inventory_preview.allow_tags = True

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('inventory_items')


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        'product_variant', 'warehouse', 'quantity_available', 'quantity_reserved',
        'reorder_level', 'stock_status', 'last_restocked', 'is_backorder_allowed'
    )
    list_filter = (
        'warehouse', 'is_backorder_allowed', 'warehouse__warehouse_type',
        'warehouse__is_operational'
    )
    search_fields = (
        'product_variant__name', 'product_variant__sku',
        'warehouse__name', 'warehouse__code', 'batch_number'
    )
    readonly_fields = (
        'last_checked', 'last_cost_update', 'inventory_value',
        'days_until_expiry_display', 'stock_movements_link'
    )
    list_per_page = 50
    filter_horizontal = ()
    ordering = ('product_variant__name', 'warehouse__name')
    date_hierarchy = 'last_restocked'
    filter_class = InventoryFilter
    list_select_related = ('product_variant', 'warehouse')

    fieldsets = (
        (_('Product & Warehouse'), {
            'fields': ('product_variant', 'warehouse')
        }),
        (_('Stock Information'), {
            'fields': (
                'quantity_available', 'quantity_reserved', 'reorder_level',
                'is_backorder_allowed', 'batch_number', 'expiry_date'
            )
        }),
        (_('Cost Information'), {
            'fields': (
                'cost_price', 'manufacturing_cost_adjustment',
                'packaging_cost_adjustment', 'shipping_cost_adjustment',
                'inventory_value', 'last_cost_update'
            )
        }),
        (_('Dates'), {
            'fields': ('last_restocked', 'last_checked'),
            'classes': ('collapse',)
        }),
        (_('Stock Movements'), {
            'fields': ('stock_movements_link',),
            'classes': ('collapse',)
        }),
    )

    def stock_status(self, obj):
        if obj.quantity_available <= 0:
            return format_html(
                '<span style="color: red; font-weight: bold;">{}</span>',
                _('Out of Stock')
            )
        elif obj.quantity_available <= obj.reorder_level:
            return format_html(
                '<span style="color: orange; font-weight: bold;">{}</span>',
                _('Low Stock')
            )
        return format_html(
            '<span style="color: green; font-weight: bold;">{}</span>',
            _('In Stock')
        )

    stock_status.short_description = _('Status')
    stock_status.admin_order_field = 'quantity_available'

    def inventory_value(self, obj):
        if obj.cost_price is not None:
            return f"${obj.inventory_value:.2f}"
        return "-"

    inventory_value.short_description = _('Total Value')

    def days_until_expiry_display(self, obj):
        if not obj.expiry_date:
            return "-"
        days = obj.days_until_expiry
        if days is None:
            return "-"
        if days < 0:
            return format_html(
                '<span style="color: red; font-weight: bold;">{} {}</span>',
                abs(days), _('days expired')
            )
        return f"{days} {_('days')}"

    days_until_expiry_display.short_description = _('Expires In')

    def stock_movements_link(self, obj):
        url = (
                reverse('admin:inventory_stockmovement_changelist') +
                f'?inventory__id__exact={obj.id}'
        )
        return format_html('<a href="{}">{}</a>', url, _('View Stock Movements'))

    stock_movements_link.short_description = _('Stock Movements')
    stock_movements_link.allow_tags = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product_variant__product', 'warehouse'
        )

    def save_model(self, request, obj, form, change):
        if 'cost_price' in form.changed_data:
            obj.last_cost_update = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'inventory_with_product', 'movement_type_display', 'quantity_display',
        'warehouse_info', 'reference', 'movement_date', 'value_display'
    )
    list_filter = (
        'movement_type',
        ('movement_date', DateRangeFilter),
        'inventory__warehouse',
        'source_warehouse',
        'destination_warehouse',
    )
    search_fields = (
        'inventory__product_variant__name',
        'inventory__product_variant__sku',
        'reference',
        'notes',
        'processed_by__email',
        'processed_by__first_name',
        'processed_by__last_name',
    )
    list_select_related = (
        'inventory__product_variant__product',
        'inventory__warehouse',
        'source_warehouse',
        'destination_warehouse',
        'processed_by',
    )
    readonly_fields = (
        'date_created',
        'date_updated',
        'total_value',
        'inventory_link',
        'source_warehouse_link',
        'destination_warehouse_link',
        'processed_by_link',
    )
    list_per_page = 50
    date_hierarchy = 'movement_date'
    ordering = ('-movement_date', '-date_created')

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'inventory_link',
                'movement_type',
                'quantity',
                'reference',
                'movement_date',
                'notes',
            )
        }),
        (_('Warehouse Information'), {
            'fields': (
                'source_warehouse_link',
                'destination_warehouse_link',
            )
        }),
        (_('Financial Information'), {
            'fields': (
                'unit_cost',
                'total_value',
            ),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': (
                'processed_by_link',
                'date_created',
                'date_updated',
            ),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'inventory__product_variant__product',
            'inventory__warehouse',
            'source_warehouse',
            'destination_warehouse',
            'processed_by',
        )

    def inventory_with_product(self, obj):
        variant = obj.inventory.product_variant
        return format_html(
            '{}<br><small class="help">{}</small>',
            variant,
            variant.product
        )

    inventory_with_product.short_description = _('Product')
    inventory_with_product.admin_order_field = 'inventory__product_variant__name'

    def movement_type_display(self, obj):
        type_icons = {
            'purchase': '📥',
            'sale': '📤',
            'return': '🔄',
            'adjustment': '📊',
            'transfer_in': '➡️',
            'transfer_out': '⬅️',
            'loss': '❌',
            'damaged': '⚠️',
            'expire': '📅',
            'count': '🔢',
        }
        return format_html(
            '{} {}',
            type_icons.get(obj.movement_type, ''),
            obj.get_movement_type_display()
        )

    movement_type_display.short_description = _('Type')

    def quantity_display(self, obj):
        css_class = 'success' if obj.quantity > 0 else 'warning'
        return format_html(
            '<span class="badge bg-{}">{:+}</span>',
            css_class,
            obj.quantity
        )

    quantity_display.short_description = _('Qty')
    quantity_display.admin_order_field = 'quantity'

    def warehouse_info(self, obj):
        if obj.source_warehouse and obj.destination_warehouse:
            return format_html(
                '{} → {}',
                obj.source_warehouse.code,
                obj.destination_warehouse.code
            )
        return obj.inventory.warehouse.code if obj.inventory.warehouse else '-'

    warehouse_info.short_description = _('Warehouse(s)')

    def value_display(self, obj):
        if obj.total_value is not None:
            return f"${obj.total_value:,.2f}"
        return "-"

    value_display.short_description = _('Value')
    value_display.admin_order_field = 'total_value'

    def inventory_link(self, obj):
        if obj.inventory_id:
            url = reverse('admin:inventory_inventory_change', args=[obj.inventory_id])
            return format_html('<a href="{}">{}</a>', url, obj.inventory)
        return "-"

    inventory_link.short_description = _('Inventory')

    def source_warehouse_link(self, obj):
        if obj.source_warehouse_id:
            url = reverse('admin:inventory_warehouseprofile_change', args=[obj.source_warehouse_id])
            return format_html('<a href="{}">{}</a>', url, obj.source_warehouse)
        return "-"

    source_warehouse_link.short_description = _('Source Warehouse')

    def destination_warehouse_link(self, obj):
        if obj.destination_warehouse_id:
            url = reverse('admin:inventory_warehouseprofile_change', args=[obj.destination_warehouse_id])
            return format_html('<a href="{}">{}</a>', url, obj.destination_warehouse)
        return "-"

    destination_warehouse_link.short_description = _('Destination Warehouse')

    def processed_by_link(self, obj):
        if obj.processed_by_id:
            url = reverse('admin:users_user_change', args=[obj.processed_by_id])
            return format_html('<a href="{}">{}</a>', url, obj.processed_by.get_full_name() or obj.processed_by.email)
        return "-"

    processed_by_link.short_description = _('Processed By')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.processed_by = request.user
        super().save_model(request, obj, form, change)

    class Media:
        css = {
            'all': (
                'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css',
            )
        }
        js = (
            'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js',
        )