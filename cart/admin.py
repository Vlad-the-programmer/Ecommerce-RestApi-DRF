from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, F, Value
from django.db.models.functions import Coalesce
from django.contrib import messages

from cart.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('get_product_name', 'unit_price', 'subtotal')
    fields = ('get_product_name', 'quantity', 'unit_price', 'subtotal')
    can_delete = False

    def get_product_name(self, obj):
        url = reverse('admin:products_product_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.product))

    get_product_name.short_description = _('Product')

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user_link', 'item_count', 'total_price', 'is_active',
        'date_created', 'date_updated'
    )
    list_filter = ('is_active', 'date_created', 'date_updated')
    search_fields = (
        'user__email', 'user__first_name', 'user__last_name', 'id'
    )
    readonly_fields = (
        'user_link', 'item_count', 'total_price', 'date_created',
        'date_updated', 'date_deleted', 'is_deleted'
    )
    inlines = [CartItemInline]
    fieldsets = (
        (_('Customer Information'), {
            'fields': ('user_link', 'is_active')
        }),
        (_('Cart Summary'), {
            'fields': ('item_count', 'total_price')
        }),
        (_('Timestamps'), {
            'classes': ('collapse',),
            'fields': ('date_created', 'date_updated', 'date_deleted', 'is_deleted')
        }),
    )
    actions = ['merge_carts', 'abandoned_carts_report']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _item_count=Coalesce(Sum('items__quantity'), Value(0)),
            _total_price=Coalesce(
                Sum(F('items__quantity') * F('items__unit_price')),
                Value(0)
            )
        )

    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html(
                '<a href="{}">{} ({})</a>',
                url,
                obj.user.get_full_name() or obj.user.email,
                obj.user.email
            )
        return _('Anonymous')

    user_link.short_description = _('User')
    user_link.admin_order_field = 'user__email'

    def item_count(self, obj):
        if hasattr(obj, '_item_count'):
            return obj._item_count
        return obj.items.aggregate(total=Sum('quantity'))['total'] or 0

    item_count.short_description = _('Items')
    item_count.admin_order_field = '_item_count'

    def total_price(self, obj):
        if hasattr(obj, '_total_price'):
            return f"${obj._total_price:,.2f}"
        total = obj.items.aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total'] or 0
        return f"${total:,.2f}"

    total_price.short_description = _('Total Price')
    total_price.admin_order_field = '_total_price'

    def merge_carts(self, request, queryset):
        if queryset.count() < 2:
            self.message_user(
                request,
                _('Please select at least 2 carts to merge.'),
                messages.WARNING
            )
            return

        # Get the target cart (the first selected)
        target_cart = queryset.first()
        other_carts = queryset.exclude(id=target_cart.id)
        merged_items = 0

        for cart in other_carts:
            # Move all items from other carts to target cart
            for item in cart.items.all():
                # Check if item already exists in target cart
                existing_item = target_cart.items.filter(
                    product=item.product
                ).first()

                if existing_item:
                    # Update quantity if item exists
                    existing_item.quantity += item.quantity
                    existing_item.save()
                    merged_items += 1
                else:
                    # Move item to target cart
                    item.cart = target_cart
                    item.save()
                    merged_items += 1

            # Deactivate merged carts
            cart.is_active = False
            cart.save()

        self.message_user(
            request,
            _('Successfully merged %(count)d carts into cart #%(id)s. %(items)d items were merged.') % {
                'count': other_carts.count(),
                'id': target_cart.id,
                'items': merged_items
            },
            messages.SUCCESS
        )

    merge_carts.short_description = _('Merge selected carts')

    def abandoned_carts_report(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(days=1)
        abandoned_carts = queryset.filter(
            date_updated__lt=cutoff,
            is_active=True
        ).select_related('user').prefetch_related('items')

        report_lines = []
        for cart in abandoned_carts:
            user_info = str(cart.user) if cart.user else 'Anonymous'
            item_count = cart.items.count()
            last_updated = cart.date_updated.strftime('%Y-%m-%d %H:%M')
            report_lines.append(
                f"Cart ID: {cart.id}, User: {user_info}, "
                f"Items: {item_count}, Last Updated: {last_updated}"
            )

        from django.http import HttpResponse
        response = HttpResponse(
            "\n".join(report_lines),
            content_type='text/plain'
        )
        response['Content-Disposition'] = 'attachment; filename=abandoned_carts_report.txt'
        return response

    abandoned_carts_report.short_description = _('Generate abandoned carts report')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'cart_link', 'product_link', 'quantity',
        'unit_price', 'subtotal', 'added_at'
    )
    list_filter = ('added_at', 'date_updated')
    search_fields = (
        'cart__user__email', 'product__name',
        'product__sku', 'cart__id'
    )
    readonly_fields = (
        'cart_link', 'product_link', 'unit_price',
        'subtotal', 'added_at', 'date_updated'
    )
    fieldsets = (
        (_('Cart & Product'), {
            'fields': ('cart_link', 'product_link')
        }),
        (_('Pricing'), {
            'fields': ('quantity', 'unit_price', 'subtotal')
        }),
        (_('Timestamps'), {
            'classes': ('collapse',),
            'fields': ('added_at', 'date_updated')
        }),
    )

    def cart_link(self, obj):
        url = reverse('admin:cart_cart_change', args=[obj.cart.id])
        return format_html('<a href="{}">Cart #{}</a>', url, obj.cart.id)

    cart_link.short_description = _('Cart')

    def product_link(self, obj):
        url = reverse('admin:products_product_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.product))

    product_link.short_description = _('Product')

    def subtotal(self, obj):
        return f"${obj.quantity * obj.unit_price:,.2f}"

    subtotal.short_description = _('Subtotal')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.cart.save()