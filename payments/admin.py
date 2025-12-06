from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Sum, Q
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path

from payments.models import Payment
from payments.enums import PaymentStatus, PaymentMethod


class PaymentStatusFilter(admin.SimpleListFilter):
    title = _('Payment Status')
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return PaymentStatus.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class PaymentMethodFilter(admin.SimpleListFilter):
    title = _('Payment Method')
    parameter_name = 'method'

    def lookups(self, request, model_admin):
        return PaymentMethod.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(method=self.value())
        return queryset


class AmountRangeFilter(admin.SimpleListFilter):
    title = _('Amount Range')
    parameter_name = 'amount_range'

    def lookups(self, request, model_admin):
        return [
            ('0-50', _('$0 - $50')),
            ('50-100', _('$50 - $100')),
            ('100-500', _('$100 - $500')),
            ('500+', _('$500+')),
        ]

    def queryset(self, request, queryset):
        if self.value() == '0-50':
            return queryset.filter(amount__range=(0, 50))
        if self.value() == '50-100':
            return queryset.filter(amount__range=(50, 100))
        if self.value() == '100-500':
            return queryset.filter(amount__range=(100, 500))
        if self.value() == '500+':
            return queryset.filter(amount__gte=500)
        return queryset


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'payment_reference', 'status_badge', 'amount_with_currency', 'invoice_link',
        'user_link', 'method_display', 'transaction_date', 'is_active'
    )
    list_filter = (
        PaymentStatusFilter, PaymentMethodFilter, AmountRangeFilter,
        'currency', 'is_active', 'transaction_date'
    )
    search_fields = (
        'payment_reference', 'invoice__invoice_number',
        'user__email', 'user__first_name', 'user__last_name',
        'notes'
    )
    readonly_fields = (
        'date_created', 'date_updated', 'date_deleted', 'is_deleted',
        'payment_reference', 'transaction_date', 'confirmed_at'
    )
    date_hierarchy = 'transaction_date'
    list_select_related = ('invoice', 'user')
    actions = [
        'mark_as_completed', 'mark_as_failed', 'mark_as_refunded',
        'mark_as_cancelled', 'export_selected_payments'
    ]
    fieldsets = (
        (_('Payment Information'), {
            'fields': (
                'payment_reference', 'amount', 'currency', 'method', 'status',
                'transaction_date', 'confirmed_at', 'notes'
            )
        }),
        (_('Relations'), {
            'fields': ('invoice', 'user')
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
        return super().get_queryset(request).select_related('invoice', 'user')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:payment_id>/complete/',
                self.admin_site.admin_view(self.process_complete),
                name='payment-complete',
            ),
            path(
                '<int:payment_id>/refund/',
                self.admin_site.admin_view(self.process_refund),
                name='payment-refund',
            ),
        ]
        return custom_urls + urls

    def process_complete(self, request, payment_id, *args, **kwargs):
        try:
            payment = Payment.objects.get(id=payment_id)
            if payment.status != PaymentStatus.COMPLETED:
                payment.mark_completed()
                self.message_user(request, _('Payment marked as completed successfully'))
            else:
                self.message_user(request, _('Payment is already completed'), messages.WARNING)
        except Payment.DoesNotExist:
            self.message_user(request, _('Payment not found'), messages.ERROR)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    def process_refund(self, request, payment_id, *args, **kwargs):
        try:
            payment = Payment.objects.get(id=payment_id)
            if payment.status == PaymentStatus.COMPLETED:
                refund_amount = request.POST.get('amount', str(payment.amount))
                refund = payment.refund(amount=refund_amount, reason='Admin refund')
                self.message_user(
                    request,
                    _('Refund processed successfully. Refund ID: %s') % refund.payment_reference
                )
            else:
                self.message_user(
                    request,
                    _('Only completed payments can be refunded'),
                    messages.ERROR
                )
        except Exception as e:
            self.message_user(request, str(e), messages.ERROR)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    def status_badge(self, obj):
        status_colors = {
            PaymentStatus.PENDING: 'orange',
            PaymentStatus.COMPLETED: 'green',
            PaymentStatus.FAILED: 'red',
            PaymentStatus.REFUNDED: 'blue',
            PaymentStatus.CANCELLED: 'gray',
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: white; background-color: {}; '
            'padding: 3px 8px; border-radius: 4px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = _('Status')
    status_badge.admin_order_field = 'status'

    def amount_with_currency(self, obj):
        return f"{obj.amount} {obj.currency}"
    amount_with_currency.short_description = _('Amount')
    amount_with_currency.admin_order_field = 'amount'

    def invoice_link(self, obj):
        if obj.invoice_id:
            url = reverse('admin:invoices_invoice_change', args=[obj.invoice_id])
            return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_number)
        return "-"
    invoice_link.short_description = _('Invoice')
    invoice_link.admin_order_field = 'invoice__invoice_number'

    def user_link(self, obj):
        if obj.user_id:
            url = reverse('admin:users_user_change', args=[obj.user_id])
            return format_html('<a href="{}">{} ({})</a>',
                             url,
                             obj.user.get_full_name() or obj.user.email,
                             obj.user_id)
        return "-"
    user_link.short_description = _('User')
    user_link.admin_order_field = 'user__email'

    def method_display(self, obj):
        return obj.get_method_display()
    method_display.short_description = _('Method')
    method_display.admin_order_field = 'method'

    def mark_as_completed(self, request, queryset):
        updated = 0
        for payment in queryset:
            if payment.status != PaymentStatus.COMPLETED:
                payment.mark_completed()
                updated += 1
        self.message_user(
            request,
            _('Successfully marked %d payments as completed.') % updated,
            messages.SUCCESS
        )
    mark_as_completed.short_description = _('Mark selected payments as completed')

    def mark_as_failed(self, request, queryset):
        updated = queryset.update(status=PaymentStatus.FAILED, is_active=False)
        self.message_user(
            request,
            _('Successfully marked %d payments as failed.') % updated,
            messages.SUCCESS
        )
    mark_as_failed.short_description = _('Mark selected payments as failed')

    def mark_as_refunded(self, request, queryset):
        updated = 0
        for payment in queryset:
            if payment.status == PaymentStatus.COMPLETED:
                payment.mark_refunded()
                updated += 1
        self.message_user(
            request,
            _('Successfully marked %d payments as refunded.') % updated,
            messages.SUCCESS
        )
    mark_as_refunded.short_description = _('Mark selected payments as refunded')

    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status=PaymentStatus.CANCELLED, is_active=False)
        self.message_user(
            request,
            _('Successfully marked %d payments as cancelled.') % updated,
            messages.SUCCESS
        )
    mark_as_cancelled.short_description = _('Mark selected payments as cancelled')

    def export_selected_payments(self, request, queryset):
        self.message_user(
            request,
            _('Export functionality would be implemented here for %d payments.') % queryset.count(),
            messages.INFO
        )
    export_selected_payments.short_description = _('Export selected payments')


class PaymentStatsAdmin(admin.ModelAdmin):
    change_list_template = 'admin/payments/payment_stats.html'
    date_hierarchy = 'transaction_date'

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(
            request,
            extra_context=extra_context or {},
        )

        try:
            qs = self.get_queryset(request)
        except Exception:
            return response

        stats = {
            'total_payments': qs.count(),
            'total_amount': qs.aggregate(total=Sum('amount'))['total'] or 0,
            'completed_payments': qs.filter(status=PaymentStatus.COMPLETED).count(),
            'pending_payments': qs.filter(status=PaymentStatus.PENDING).count(),
            'failed_payments': qs.filter(status=PaymentStatus.FAILED).count(),
            'refunded_payments': qs.filter(status=PaymentStatus.REFUNDED).count(),
        }

        payment_methods = qs.values('method').annotate(
            count=Count('id'),
            total=Sum('amount')
        ).order_by('-total')

        monthly_revenue = qs.filter(status=PaymentStatus.COMPLETED).extra({
            'month': "date_trunc('month', transaction_date)"
        }).values('month').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('month')

        if not isinstance(response.context_data, dict):
            response.context_data = {}

        response.context_data.update({
            'stats': stats,
            'payment_methods': payment_methods,
            'monthly_revenue': monthly_revenue,
            'title': _('Payment Statistics'),
        })

        return response


admin.site.register(Payment, PaymentStatsAdmin)