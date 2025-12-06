from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path

from .models import Refund, RefundItem
from .enums import RefundStatus


class StatusFilter(admin.SimpleListFilter):
    title = _('Status')
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return RefundStatus.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class AmountRangeFilter(admin.SimpleListFilter):
    title = _('Amount Range')
    parameter_name = 'amount_range'

    def lookups(self, request, model_admin):
        return [
            ('0-100', _('$0 - $100')),
            ('100-500', _('$100 - $500')),
            ('500-1000', _('$500 - $1,000')),
            ('1000+', _('$1,000+')),
        ]

    def queryset(self, request, queryset):
        if self.value() == '0-100':
            return queryset.filter(amount_requested__range=(0, 100))
        if self.value() == '100-500':
            return queryset.filter(amount_requested__range=(100, 500))
        if self.value() == '500-1000':
            return queryset.filter(amount_requested__range=(500, 1000))
        if self.value() == '1000+':
            return queryset.filter(amount_requested__gte=1000)
        return queryset


class RefundItemInline(admin.TabularInline):
    model = RefundItem
    extra = 0
    readonly_fields = ('order_item', 'quantity', 'unit_price', 'amount', 'reason')
    fields = ('order_item', 'quantity', 'unit_price', 'amount', 'reason')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = (
        'refund_number', 'status_badge', 'order_link', 'user_link',
        'amount_display', 'date_created', 'processed_by_display'
    )
    list_filter = (
        StatusFilter, AmountRangeFilter, 'currency', 'is_active',
        'date_created', 'processed_at'
    )
    search_fields = (
        'refund_number', 'order__order_number',
        'customer__email', 'customer__first_name', 'customer__last_name'
    )
    readonly_fields = (
        'refund_number', 'date_created', 'date_updated', 'date_deleted',
        'status_display', 'amount_display', 'order_link', 'user_link',
        'payment_link', 'processed_by_display', 'is_deleted'
    )
    date_hierarchy = 'date_created'
    list_select_related = ('order', 'customer', 'payment', 'processed_by')
    inlines = [RefundItemInline]
    actions = [
        'approve_selected', 'reject_selected', 'cancel_selected',
        'complete_selected', 'export_selected_refunds'
    ]
    fieldsets = (
        (_('Refund Information'), {
            'fields': (
                'refund_number', 'status_display', 'order_link', 'user_link',
                'payment_link', 'amount_display', 'currency', 'reason', 'refund_method'
            )
        }),
        (_('Processing Details'), {
            'fields': (
                'processed_by_display', 'processed_at', 'date_completed',
                'amount_refunded', 'rejection_reason', 'refund_receipt'
            )
        }),
        (_('Notes'), {
            'classes': ('collapse',),
            'fields': ('customer_notes', 'internal_notes')
        }),
        (_('Status'), {
            'fields': ('is_active', 'is_deleted', 'date_deleted')
        }),
        (_('Timestamps'), {
            'classes': ('collapse',),
            'fields': ('date_created', 'date_updated')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'order', 'user', 'payment', 'processed_by'
        ).prefetch_related('items')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:refund_id>/process/',
                self.admin_site.admin_view(self.process_refund),
                name='refund-process',
            ),
        ]
        return custom_urls + urls

    def status_badge(self, obj):
        status_colors = {
            RefundStatus.PENDING: 'gray',
            RefundStatus.APPROVED: 'blue',
            RefundStatus.REJECTED: 'red',
            RefundStatus.COMPLETED: 'green',
            RefundStatus.CANCELLED: 'orange',
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: white; background-color: {}; '
            'padding: 3px 8px; border-radius: 4px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = _('Status')
    status_badge.admin_order_field = 'status'

    def amount_display(self, obj):
        return f"{obj.currency} {obj.amount_requested:.2f}"
    amount_display.short_description = _('Amount')
    amount_display.admin_order_field = 'amount_requested'

    def order_link(self, obj):
        if obj.order_id:
            url = reverse('admin:orders_order_change', args=[obj.order_id])
            return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
        return "-"
    order_link.short_description = _('Order')
    order_link.admin_order_field = 'order__order_number'

    def user_link(self, obj):
        if obj.user_id:
            url = reverse('admin:users_user_change', args=[obj.user_id])
            return format_html(
                '<a href="{}">{} ({})</a>',
                url,
                obj.user.get_full_name() or obj.user.email,
                obj.user_id
            )
        return "-"
    user_link.short_description = _('User')
    user_link.admin_order_field = 'user__email'

    def payment_link(self, obj):
        if obj.payment_id:
            url = reverse('admin:payments_payment_change', args=[obj.payment_id])
            return format_html('<a href="{}">{}</a>', url, obj.payment_id)
        return "-"
    payment_link.short_description = _('Payment')

    def processed_by_display(self, obj):
        if obj.processed_by_id:
            url = reverse('admin:users_user_change', args=[obj.processed_by_id])
            return format_html(
                '<a href="{}">{}</a>',
                url,
                obj.processed_by.get_full_name() or obj.processed_by.email
            )
        return "-"
    processed_by_display.short_description = _('Processed By')

    def status_display(self, obj):
        return obj.get_status_display()
    status_display.short_description = _('Status')

    def approve_selected(self, request, queryset):
        updated = 0
        for refund in queryset:
            if refund.status == RefundStatus.PENDING:
                refund.approve(processed_by=request.user)
                updated += 1
        self.message_user(
            request,
            _('Successfully approved %d refunds.') % updated,
            messages.SUCCESS
        )
    approve_selected.short_description = _('Approve selected refunds')

    def reject_selected(self, request, queryset):
        updated = 0
        for refund in queryset:
            if refund.status == RefundStatus.PENDING:
                refund.reject(rejection_reason="Bulk rejection", rejected_by=request.user)
                updated += 1
        self.message_user(
            request,
            _('Successfully rejected %d refunds.') % updated,
            messages.SUCCESS
        )
    reject_selected.short_description = _('Reject selected refunds')

    def cancel_selected(self, request, queryset):
        updated = 0
        for refund in queryset:
            if refund.status in [RefundStatus.PENDING, RefundStatus.APPROVED]:
                refund.cancel(cancelled_by=request.user)
                updated += 1
        self.message_user(
            request,
            _('Successfully cancelled %d refunds.') % updated,
            messages.SUCCESS
        )
    cancel_selected.short_description = _('Cancel selected refunds')

    def complete_selected(self, request, queryset):
        updated = 0
        for refund in queryset:
            if refund.status == RefundStatus.APPROVED:
                refund.complete(completed_by=request.user)
                updated += 1
        self.message_user(
            request,
            _('Successfully completed %d refunds.') % updated,
            messages.SUCCESS
        )
    complete_selected.short_description = _('Complete selected refunds')

    def export_selected_refunds(self, request, queryset):
        # TODO: Implement export functionality
        self.message_user(
            request,
            _('Export functionality would be implemented here for %d refunds.') % queryset.count(),
            messages.INFO
        )
    export_selected_refunds.short_description = _('Export selected refunds')

    def process_refund(self, request, refund_id, *args, **kwargs):
        """Handle refund processing from admin."""
        try:
            refund = Refund.objects.get(id=refund_id)
            if refund.status == RefundStatus.APPROVED:
                refund.complete(completed_by=request.user)
                self.message_user(request, _('Refund processed successfully'))
            else:
                self.message_user(
                    request,
                    _('Only approved refunds can be processed'),
                    messages.WARNING
                )
        except Refund.DoesNotExist:
            self.message_user(request, _('Refund not found'), messages.ERROR)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))