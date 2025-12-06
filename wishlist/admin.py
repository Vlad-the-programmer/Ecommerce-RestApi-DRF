from django.contrib import admin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

from .models import Wishlist, WishListItem, WishListItemPriority


class WishlistItemInline(admin.TabularInline):
    """Inline admin for wishlist items."""
    model = WishListItem
    extra = 0
    fields = ('product', 'variant', 'quantity', 'priority', 'date_created')
    readonly_fields = ('date_created',)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    """Admin configuration for Wishlist model."""
    list_display = ('id', 'user_display', 'name', 'is_public', 'items_count', 'date_created')
    list_filter = ('is_public', 'date_created', 'date_updated')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'name')
    readonly_fields = ('date_created', 'date_updated', 'items_count')
    list_select_related = ('user',)
    inlines = (WishlistItemInline,)
    fieldsets = (
        (None, {
            'fields': ('user', 'name', 'is_public')
        }),
        (_('Metadata'), {
            'fields': ('date_created', 'date_updated', 'items_count'),
            'classes': ('collapse',)
        }),
    )

    def user_display(self, obj):
        if obj.user:
            return f"{obj.user.get_full_name()} ({obj.user.email})"
        return _("Guest")
    user_display.short_description = _('User')
    user_display.admin_order_field = 'user__email'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('wishlist_items')


@admin.register(WishListItem)
class WishlistItemAdmin(admin.ModelAdmin):
    """Admin configuration for WishlistItem model."""
    list_display = ('id', 'wishlist_link', 'product_link', 'variant_display', 
                   'quantity', 'priority_display', 'date_created')
    list_filter = ('priority', 'date_created')
    search_fields = (
        'wishlist__user__email', 
        'product__name', 
        'variant__name',
        'wishlist__name'
    )
    readonly_fields = ('date_created', 'date_updated')
    list_select_related = ('wishlist', 'product', 'variant', 'wishlist__user')
    fieldsets = (
        (None, {
            'fields': ('wishlist', 'product', 'variant', 'quantity', 'note', 'priority')
        }),
        (_('Metadata'), {
            'fields': ('date_created', 'date_updated'),
            'classes': ('collapse',)
        }),
    )

    def wishlist_link(self, obj):
        url = reverse('admin:wishlist_wishlist_change', args=[obj.wishlist.id])
        return format_html('<a href="{}">{}</a>', url, obj.wishlist)
    wishlist_link.short_description = _('Wishlist')
    wishlist_link.admin_order_field = 'wishlist__id'

    def product_link(self, obj):
        url = reverse('admin:products_product_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product)
    product_link.short_description = _('Product')
    product_link.admin_order_field = 'product__name'

    def variant_display(self, obj):
        return obj.variant or "-"
    variant_display.short_description = _('Variant')
    variant_display.admin_order_field = 'variant__name'

    def priority_display(self, obj):
        return dict(WishListItemPriority.choices).get(obj.priority, '-')
    priority_display.short_description = _('Priority')
    priority_display.admin_order_field = 'priority'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'variant', 'wishlist__user')
