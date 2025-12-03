from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from orders.models import Order, OrderItem, OrderTax, OrderStatusHistory
from orders.enums import OrderStatuses
from orders.filters import OrderItemFilter, OrderStatusHistoryFilter, OrderTaxFilter


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('get_product_name', 'get_variant_name', 'quantity', 'total_price')
    fields = ('get_product_name', 'get_variant_name', 'quantity', 'total_price')
    show_change_link = True
    
    def get_product_name(self, obj):
        return str(obj.product) if obj.product else "-"
    get_product_name.short_description = _("Product")
    
    def get_variant_name(self, obj):
        return str(obj.variant) if obj.variant else "-"
    get_variant_name.short_description = _("Variant")
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


class OrderTaxInline(admin.TabularInline):
    model = OrderTax
    extra = 0
    readonly_fields = ('name', 'rate', 'amount', 'tax_value', 'amount_with_taxes')
    fields = ('name', 'rate', 'amount', 'tax_value', 'amount_with_taxes')
    show_change_link = True



class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ('status', 'notes', 'changed_by', 'date_created')
    fields = ('status', 'notes', 'changed_by', 'date_created')
    show_change_link = True


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number', 'user_info', 'status', 'display_total_amount', 
        'date_created', 'display_items_count', 'view_order_link'
    )
    list_filter = ('status', 'date_created', 'date_updated')
    search_fields = (
        'order_number', 'user__email', 'user__first_name', 'user__last_name',
        'shipping_address__first_name', 'shipping_address__last_name',
        'shipping_address__email', 'shipping_address__phone'
    )
    readonly_fields = (
        'order_number', 'user', 'cart', 'date_created', 'date_updated',
        'display_items_count', 'display_total_amount', 'display_order_items',
        'display_order_taxes', 'display_status_history', 'view_order_in_admin'
    )
    fieldsets = (
        (_('Order Information'), {
            'fields': (
                'order_number', 'user', 'status', 'date_created', 'date_updated',
                'display_total_amount', 'display_items_count', 'view_order_in_admin'
            )
        }),
        (_('Shipping Information'), {
            'fields': ('shipping_class', 'shipping_address'),
            'classes': ('collapse',)
        }),
        (_('Items'), {
            'fields': ('display_order_items',),
            'classes': ('collapse',)
        }),
        (_('Taxes'), {
            'fields': ('display_order_taxes',),
            'classes': ('collapse',)
        }),
        (_('Status History'), {
            'fields': ('display_status_history',),
            'classes': ('collapse',)
        }),
    )
    inlines = [OrderItemInline, OrderTaxInline, OrderStatusHistoryInline]
    actions = [
        'mark_as_paid', 'mark_as_shipped', 'mark_as_delivered', 
        'mark_as_completed', 'mark_as_cancelled', 'mark_as_refunded'
    ]
    list_per_page = 25
    date_hierarchy = 'date_created'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'shipping_class', 'shipping_address'
        ).prefetch_related('order_items', 'order_taxes')
    
    def user_info(self, obj):
        if obj.user:
            return f"{obj.user.get_full_name() or obj.user.email}"
        return "-"
    user_info.short_description = _('Customer')
    user_info.admin_order_field = 'user__email'
    
    def display_total_amount(self, obj):
        return f"${obj.total_amount:.2f}" if obj.total_amount else "-"
    display_total_amount.short_description = _('Total Amount')
    display_total_amount.admin_order_field = 'total_amount'
    
    def display_items_count(self, obj):
        return obj.order_items.count()
    display_items_count.short_description = _('Items')
    
    def display_order_items(self, obj):
        items = obj.order_items.select_related('product', 'variant').all()
        if not items:
            return _("No items in this order.")
            
        item_list = []
        for item in items:
            item_list.append(
                f"{item.quantity}x {item.product} - {item.variant if item.variant else ''} "
                f"(${item.total_price:.2f})"
            )
        return mark_safe('<br>'.join(item_list))
    display_order_items.short_description = _('Order Items')
    
    def display_order_taxes(self, obj):
        taxes = obj.order_taxes.all()
        if not taxes:
            return _("No taxes applied to this order.")
            
        tax_list = []
        for tax in taxes:
            tax_list.append(
                f"{tax.name} ({tax.rate*100}%): ${tax.tax_value:.2f} "
                f"(on ${tax.amount:.2f} = ${tax.amount_with_taxes:.2f})"
            )
        return mark_safe('<br>'.join(tax_list))
    display_order_taxes.short_description = _('Order Taxes')
    
    def display_status_history(self, obj):
        history = obj.order_status_history.select_related('changed_by').order_by('-date_created')
        if not history:
            return _("No status history available.")
            
        history_list = []
        for entry in history:
            history_list.append(
                f"{entry.get_status_display()} - {entry.date_created.strftime('%Y-%m-%d %H:%M')} "
                f"by {entry.changed_by.get_full_name() or entry.changed_by.email if entry.changed_by else 'System'}"
                f"{': ' + entry.notes if entry.notes else ''}"
            )
        return mark_safe('<br>'.join(history_list))
    display_status_history.short_description = _('Status History')
    
    def view_order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.id])
        return format_html('<a href="{}">{}</a>', url, _("View Order"))
    view_order_link.short_description = ''
    view_order_link.allow_tags = True
    
    def view_order_in_admin(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.id])
        return format_html('<a class="button" href="{}">{}</a>', url, _("View in Admin"))
    view_order_in_admin.short_description = ''
    view_order_in_admin.allow_tags = True
    
    def mark_as_paid(self, request, queryset):
        updated = 0
        for order in queryset:
            if order.status != OrderStatuses.PAID:
                order.mark_paid()
                updated += 1
        self.message_user(request, _("Successfully marked %d orders as paid.") % updated)
    mark_as_paid.short_description = _("Mark selected orders as paid")
    
    def mark_as_shipped(self, request, queryset):
        updated = 0
        for order in queryset:
            if order.status != OrderStatuses.SHIPPED:
                order.mark_shipped()
                updated += 1
        self.message_user(request, _("Successfully marked %d orders as shipped.") % updated)
    mark_as_shipped.short_description = _("Mark selected orders as shipped")
    
    def mark_as_delivered(self, request, queryset):
        updated = 0
        for order in queryset:
            if order.status != OrderStatuses.DELIVERED:
                order.mark_delivered()
                updated += 1
        self.message_user(request, _("Successfully marked %d orders as delivered.") % updated)
    mark_as_delivered.short_description = _("Mark selected orders as delivered")
    
    def mark_as_completed(self, request, queryset):
        updated = 0
        for order in queryset:
            if order.status != OrderStatuses.COMPLETED:
                order.mark_completed()
                updated += 1
        self.message_user(request, _("Successfully marked %d orders as completed.") % updated)
    mark_as_completed.short_description = _("Mark selected orders as completed")
    
    def mark_as_cancelled(self, request, queryset):
        updated = 0
        for order in queryset:
            if order.status != OrderStatuses.CANCELLED and order.can_be_cancelled():
                order.cancel()
                updated += 1
        self.message_user(request, _("Successfully cancelled %d orders.") % updated)
    mark_as_cancelled.short_description = _("Cancel selected orders")
    
    def mark_as_refunded(self, request, queryset):
        updated = 0
        for order in queryset:
            if order.status != OrderStatuses.REFUNDED:
                order.mark_refunded()
                updated += 1
        self.message_user(request, _("Successfully marked %d orders as refunded.") % updated)
    mark_as_refunded.short_description = _("Mark selected orders as refunded")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_link', 'product_link',
                    'variant_link', 'quantity',
                    'display_total_price', 'date_created')
    list_filter = (
        'product',
        'variant',
        'date_created',
    )
    search_fields = (
        'order__order_number', 'product__name', 'variant__name',
        'product__sku', 'variant__sku'
    )
    readonly_fields = ('order_link', 'product_link', 'variant_link',
                       'quantity', 'display_total_price', 'date_created')
    list_select_related = ('order', 'product', 'variant')
    
    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = _('Order')
    order_link.admin_order_field = 'order__order_number'
    
    def product_link(self, obj):
        if not obj.product:
            return "-"
        url = reverse('admin:products_product_change', args=[obj.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product)
    product_link.short_description = _('Product')
    product_link.admin_order_field = 'product__name'
    
    def variant_link(self, obj):
        if not obj.variant:
            return "-"
        url = reverse('admin:products_productvariant_change', args=[obj.variant_id])
        return format_html('<a href="{}">{}</a>', url, obj.variant)
    variant_link.short_description = _('Variant')
    variant_link.admin_order_field = 'variant__name'
    
    def display_total_price(self, obj):
        return f"${obj.total_price:.2f}" if obj.total_price else "-"
    display_total_price.short_description = _('Total Price')
    display_total_price.admin_order_field = 'total_price'


@admin.register(OrderTax)
class OrderTaxAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_link', 'name', 'display_rate',
                    'display_amount', 'display_tax_value',
                    'display_amount_with_taxes')
    list_filter = (
        'name',
        'date_created',
    )
    search_fields = ('order__order_number', 'name')
    readonly_fields = ('order_link', 'name', 'display_rate',
                       'display_amount', 'display_tax_value',
                       'display_amount_with_taxes', 'date_created')
    
    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = _('Order')
    order_link.admin_order_field = 'order__order_number'
    
    def display_rate(self, obj):
        return f"{obj.rate*100:.2f}%"
    display_rate.short_description = _('Rate')
    
    def display_amount(self, obj):
        return f"${obj.amount:.2f}" if obj.amount is not None else "-"
    display_amount.short_description = _('Amount')
    
    def display_tax_value(self, obj):
        return f"${obj.tax_value:.2f}" if obj.tax_value is not None else "-"
    display_tax_value.short_description = _('Tax Value')
    
    def display_amount_with_taxes(self, obj):
        return f"${obj.amount_with_taxes:.2f}" if obj.amount_with_taxes is not None else "-"
    display_amount_with_taxes.short_description = _('Amount with Taxes')


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_link', 'status_display', 'changed_by_display', 'date_created')
    list_filter = (
        'status',
        'date_created',
    )
    search_fields = ('order__order_number', 'changed_by__email', 'changed_by__username', 'notes')
    readonly_fields = ('order_link', 'status_display', 'changed_by_display', 'notes', 'date_created')
    list_select_related = ('order', 'changed_by')
    
    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)

    order_link.short_description = _('Order')
    order_link.admin_order_field = 'order__order_number'
    
    def status_display(self, obj):
        return obj.get_status_display()
    status_display.short_description = _('Status')
    status_display.admin_order_field = 'status'
    
    def changed_by_display(self, obj):
        if not obj.changed_by:
            return _("System")
        return f"{obj.changed_by.get_full_name() or obj.changed_by.email}"
    changed_by_display.short_description = _('Changed By')
    changed_by_display.admin_order_field = 'changed_by__email'
