from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Product, ProductVariant, ProductImage, Location
from .enums import StockStatus


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image_preview', 'image', 'alt_text', 'display_order', 'is_primary')
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" style="object-fit: cover;" />', obj.image.url)
        return "No Image"
    image_preview.short_description = 'Preview'


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ('sku', 'color', 'size', 'cost_price', 'price_adjustment', 'stock_quantity', 'in_stock')
    readonly_fields = ('in_stock',)
    
    def in_stock(self, obj):
        return obj.stock_quantity > 0
    in_stock.boolean = True


class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'product_name', 'category', 'price', 'status', 'stock_status', 
        'in_stock', 'date_created', 'date_updated'
    )
    list_filter = (
        'status', 'stock_status', 'label', 'product_type', 
        'category', 'date_created', 'date_updated'
    )
    search_fields = ('product_name', 'sku', 'barcode', 'product_description')
    list_editable = ('status', 'stock_status')
    readonly_fields = ('date_created', 'date_updated')
    prepopulated_fields = {'slug': ('product_name',)}
    inlines = [ProductVariantInline, ProductImageInline]
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('product_name', 'slug', 'product_description', 'category', 'subcategories')
        }),
        (_('Pricing'), {
            'fields': ('price', 'compare_at_price', 'cost_price')
        }),
        (_('Inventory'), {
            'fields': ('stock_status', 'track_inventory', 'low_stock_threshold')
        }),
        (_('Product Type'), {
            'fields': ('product_type', 'condition', 'label')
        }),
        (_('Shipping'), {
            'fields': ('weight', 'dimensions', 'requires_shipping')
        }),
        (_('Status'), {
            'fields': ('status', 'is_active', 'is_deleted')
        }),
        (_('Timestamps'), {
            'fields': ('date_created', 'date_updated'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category')
    
    def in_stock(self, obj):
        return obj.stock_status == StockStatus.IN_STOCK
    in_stock.boolean = True
    
    def save_model(self, request, obj, form, change):
        if obj.stock_quantity <= 0 and obj.stock_status != StockStatus.OUT_OF_STOCK:
            obj.stock_status = StockStatus.OUT_OF_STOCK
        elif obj.stock_quantity > 0 and obj.stock_status == StockStatus.OUT_OF_STOCK:
            obj.stock_status = StockStatus.IN_STOCK
        super().save_model(request, obj, form, change)


class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('sku', 'product', 'color', 'size', 'price_adjustment', 'stock_quantity', 'in_stock')
    list_filter = ('product', 'color', 'size')
    search_fields = ('sku', 'product__product_name', 'barcode')
    list_editable = ('stock_quantity', 'price_adjustment')
    readonly_fields = ('in_stock', 'date_created', 'date_updated')
    
    def in_stock(self, obj):
        return obj.stock_quantity > 0
    in_stock.boolean = True


class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image_preview', 'is_primary', 'display_order')
    list_filter = ('is_primary', 'product')
    search_fields = ('product__product_name', 'alt_text')
    list_editable = ('is_primary', 'display_order')
    readonly_fields = ('image_preview', 'date_created', 'date_updated')
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" style="object-fit: cover;" />', obj.image.url)
        return "No Image"
    image_preview.short_description = 'Preview'


class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'country', 'is_active', 'date_created')
    list_filter = ('is_active', 'country', 'city')
    search_fields = ('name', 'street_address', 'city', 'country')
    list_editable = ('is_active',)
    readonly_fields = ('date_created', 'date_updated')


admin.site.register(Product, ProductAdmin)
admin.site.register(ProductVariant, ProductVariantAdmin)
admin.site.register(ProductImage, ProductImageAdmin)
admin.site.register(Location, LocationAdmin)
