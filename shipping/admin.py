from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import InternationalRate, ShippingClass


@admin.register(InternationalRate)
class InternationalRateAdmin(admin.ModelAdmin):
    list_display = ('country', 'surcharge_display', 'is_active', 'date_created')
    list_filter = ('is_active', 'date_created')
    search_fields = ('country__name', 'country__code')
    readonly_fields = ('date_created', 'date_updated', 'date_deleted')
    list_select_related = ('country',)
    actions = ['deactivate_rates', 'activate_rates']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('country', 'surcharge', 'is_active')
        }),
        (_('Timestamps'), {
            'classes': ('collapse',),
            'fields': ('date_created', 'date_updated', 'date_deleted')
        }),
    )

    def surcharge_display(self, obj):
        return f"${obj.surcharge:,.2f}"

    surcharge_display.short_description = _('Surcharge')
    surcharge_display.admin_order_field = 'surcharge'

    def deactivate_rates(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _('Successfully deactivated %d rates.') % updated,
            admin.messages.SUCCESS
        )

    deactivate_rates.short_description = _('Deactivate selected rates')

    def activate_rates(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            _('Successfully activated %d rates.') % updated,
            admin.messages.SUCCESS
        )

    activate_rates.short_description = _('Activate selected rates')

    def delete_queryset(self, request, queryset):
        deleted = 0
        for obj in queryset:
            can_delete, reason = obj.can_be_deleted()
            if can_delete:
                obj.delete()
                deleted += 1
            else:
                self.message_user(
                    request,
                    _('Could not delete rate for %(country)s: %(reason)s') % {
                        'country': obj.country,
                        'reason': reason
                    },
                    admin.messages.WARNING
                )
        if deleted > 0:
            self.message_user(
                request,
                _('Successfully deleted %d rates.') % deleted,
                admin.messages.SUCCESS
            )


class ShippingRateInline(admin.TabularInline):
    model = ShippingClass.available_countries.through
    extra = 1
    verbose_name = _('Available Country')
    verbose_name_plural = _('Available Countries')
    autocomplete_fields = ('country',)


@admin.register(ShippingClass)
class ShippingClassAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'shipping_type', 'base_cost_display', 'delivery_timeframe',
        'is_active', 'date_created'
    )
    list_filter = (
        'is_active', 'shipping_type', 'carrier_type', 'domestic_only',
        'tracking_available', 'signature_required', 'insurance_included',
        'date_created'
    )
    search_fields = ('name', 'description', 'shipping_notes')
    readonly_fields = (
        'date_created', 'date_updated', 'date_deleted', 'delivery_speed',
        'is_free_shipping_available'
    )
    filter_horizontal = ('available_countries',)
    inlines = [ShippingRateInline]
    actions = [
        'activate_shipping', 'deactivate_shipping',
        'enable_tracking', 'disable_tracking'
    ]

    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'name', 'customer', 'shipping_address', 'shipping_notes',
                'base_cost', 'shipping_type', 'carrier_type', 'is_active'
            )
        }),
        (_('Delivery Information'), {
            'fields': (
                'estimated_days_min', 'estimated_days_max',
                'handling_time_days', 'delivery_speed'
            )
        }),
        (_('Pricing & Weight'), {
            'fields': (
                'cost_per_kg', 'free_shipping_threshold',
                'is_free_shipping_available', 'max_weight_kg', 'max_dimensions'
            )
        }),
        (_('Service Features'), {
            'classes': ('collapse',),
            'fields': (
                'tracking_available', 'signature_required',
                'insurance_included', 'insurance_cost'
            )
        }),
        (_('Regional Settings'), {
            'classes': ('collapse',),
            'fields': ('domestic_only', 'available_countries')
        }),
        (_('Timestamps'), {
            'classes': ('collapse',),
            'fields': ('date_created', 'date_updated', 'date_deleted')
        }),
    )

    def base_cost_display(self, obj):
        return f"${obj.base_cost:,.2f}"

    base_cost_display.short_description = _('Base Cost')
    base_cost_display.admin_order_field = 'base_cost'

    def delivery_timeframe(self, obj):
        return obj.get_estimated_delivery()

    delivery_timeframe.short_description = _('Delivery Time')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'customer', 'shipping_address'
        ).prefetch_related('available_countries')

    def activate_shipping(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            _('Successfully activated %d shipping classes.') % updated,
            admin.messages.SUCCESS
        )

    activate_shipping.short_description = _('Activate selected shipping classes')

    def deactivate_shipping(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _('Successfully deactivated %d shipping classes.') % updated,
            admin.messages.SUCCESS
        )

    deactivate_shipping.short_description = _('Deactivate selected shipping classes')

    def enable_tracking(self, request, queryset):
        updated = queryset.update(tracking_available=True)
        self.message_user(
            request,
            _('Enabled tracking for %d shipping classes.') % updated,
            admin.messages.SUCCESS
        )

    enable_tracking.short_description = _('Enable tracking for selected')

    def disable_tracking(self, request, queryset):
        updated = queryset.update(tracking_available=False)
        self.message_user(
            request,
            _('Disabled tracking for %d shipping classes.') % updated,
            admin.messages.SUCCESS
        )

    disable_tracking.short_description = _('Disable tracking for selected')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.customer = request.user
        super().save_model(request, obj, form, change)