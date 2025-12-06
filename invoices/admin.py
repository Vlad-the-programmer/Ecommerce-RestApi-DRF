from datetime import timedelta

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Sum
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path
from django.utils import timezone

from invoices.models import Invoice
from invoices.enums import InvoiceStatus


class StatusFilter(admin.SimpleListFilter):
    title = _('Status')
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return InvoiceStatus.choices

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
            return queryset.filter(total_amount__range=(0, 100))
        if self.value() == '100-500':
            return queryset.filter(total_amount__range=(100, 500))
        if self.value() == '500-1000':
            return queryset.filter(total_amount__range=(500, 1000))
        if self.value() == '1000+':
            return queryset.filter(total_amount__gte=1000)
        return queryset


class DueDateFilter(admin.SimpleListFilter):
    title = _('Due Date')
    parameter_name = 'due_date'

    def lookups(self, request, model_admin):
        return [
            ('today', _('Due Today')),
            ('week', _('Due This Week')),
            ('overdue', _('Overdue')),
            ('future', _('Future Dues')),
        ]

    def queryset(self, request, queryset):
        today = timezone.now().date()
        if self.value() == 'today':
            return queryset.filter(due_date=today)
        if self.value() == 'week':
            week_end = today + timedelta(days=7)
            return queryset.filter(due_date__range=[today, week_end])
        if self.value() == 'overdue':
            return queryset.filter(due_date__lt=today, status__in=[InvoiceStatus.DRAFT, InvoiceStatus.ISSUED])
        if self.value() == 'future':
            return queryset.filter(due_date__gt=today)
        return queryset


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_number', 'status_badge', 'total_with_currency', 'user_link',
        'order_link', 'issue_date', 'due_date', 'days_until_due', 'is_active'
    )
    list_filter = (
        StatusFilter, AmountRangeFilter, DueDateFilter,
        'currency', 'is_active', 'issue_date', 'due_date'
    )
    search_fields = (
        'invoice_number', 'user__email', 'user__first_name', 'user__last_name',
        'order__order_number', 'notes'
    )
    readonly_fields = (
        'date_created', 'date_updated', 'date_deleted', 'is_deleted',
        'invoice_number', 'days_until_due_display'
    )
    date_hierarchy = 'issue_date'
    list_select_related = ('user', 'order')
    actions = [
        'mark_as_issued', 'mark_as_paid', 'mark_as_overdue',
        'mark_as_cancelled', 'export_selected_invoices'
    ]
    fieldsets = (
        (_('Invoice Information'), {
            'fields': (
                'invoice_number', 'total_amount', 'currency', 'status',
                'issue_date', 'due_date', 'days_until_due_display', 'notes'
            )
        }),
        (_('Relations'), {
            'fields': ('user', 'order')
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
        return super().get_queryset(request).select_related('user', 'order')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:invoice_id>/issue/',
                self.admin_site.admin_view(self.process_issue),
                name='invoice-issue',
            ),
            path(
                '<int:invoice_id>/mark_paid/',
                self.admin_site.admin_view(self.process_mark_paid),
                name='invoice-mark-paid',
            ),
        ]
        return custom_urls + urls

    def process_issue(self, request, invoice_id, *args, **kwargs):
        try:
            invoice = Invoice.objects.get(id=invoice_id)
            if invoice.status == InvoiceStatus.DRAFT:
                invoice.mark_issued()
                self.message_user(request, _('Invoice marked as issued successfully'))
            else:
                self.message_user(request, _('Only draft invoices can be issued'), messages.WARNING)
        except Invoice.DoesNotExist:
            self.message_user(request, _('Invoice not found'), messages.ERROR)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    def process_mark_paid(self, request, invoice_id, *args, **kwargs):
        try:
            invoice = Invoice.objects.get(id=invoice_id)
            if invoice.status in [InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE]:
                invoice.mark_paid()
                self.message_user(request, _('Invoice marked as paid successfully'))
            else:
                self.message_user(
                    request,
                    _('Only issued or overdue invoices can be marked as paid'),
                    messages.WARNING
                )
        except Invoice.DoesNotExist:
            self.message_user(request, _('Invoice not found'), messages.ERROR)
        except Exception as e:
            self.message_user(request, str(e), messages.ERROR)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    def status_badge(self, obj):
        status_colors = {
            InvoiceStatus.DRAFT: 'gray',
            InvoiceStatus.ISSUED: 'blue',
            InvoiceStatus.OVERDUE: 'orange',
            InvoiceStatus.PAID: 'green',
            InvoiceStatus.CANCELLED: 'red',
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: white; background-color: {}; '
            'padding: 3px 8px; border-radius: 4px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = _('Status')
    status_badge.admin_order_field = 'status'

    def total_with_currency(self, obj):
        return f"{obj.total_amount} {obj.currency}"
    total_with_currency.short_description = _('Total')
    total_with_currency.admin_order_field = 'total_amount'

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

    def order_link(self, obj):
        if obj.order_id:
            url = reverse('admin:orders_order_change', args=[obj.order_id])
            return format_html(
                '<a href="{}">{}</a>',
                url,
                obj.order.order_number if hasattr(obj, 'order') and obj.order else '-'
            )
        return "-"
    order_link.short_description = _('Order')
    order_link.admin_order_field = 'order__order_number'

    def days_until_due(self, obj):
        days = obj.days_until_due
        if days < 0:
            return format_html('<span style="color: red;">{} {}</span>', abs(days), _('days overdue'))
        return f"{days} {_('days')}"
    days_until_due.short_description = _('Due In')
    days_until_due.admin_order_field = 'due_date'

    def days_until_due_display(self, obj):
        return self.days_until_due(obj)
    days_until_due_display.short_description = _('Due In')

    def mark_as_issued(self, request, queryset):
        updated = 0
        for invoice in queryset:
            if invoice.status == InvoiceStatus.DRAFT:
                invoice.mark_issued()
                updated += 1
        self.message_user(
            request,
            _('Successfully marked %d invoices as issued.') % updated,
            messages.SUCCESS
        )
    mark_as_issued.short_description = _('Mark selected invoices as issued')

    def mark_as_paid(self, request, queryset):
        updated = 0
        for invoice in queryset:
            if invoice.status in [InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE]:
                invoice.mark_paid()
                updated += 1
        self.message_user(
            request,
            _('Successfully marked %d invoices as paid.') % updated,
            messages.SUCCESS
        )
    mark_as_paid.short_description = _('Mark selected invoices as paid')

    def mark_as_overdue(self, request, queryset):
        updated = 0
        for invoice in queryset:
            if invoice.status == InvoiceStatus.ISSUED and invoice.due_date < timezone.now().date():
                invoice.mark_overdue()
                updated += 1
        self.message_user(
            request,
            _('Successfully marked %d invoices as overdue.') % updated,
            messages.SUCCESS
        )
    mark_as_overdue.short_description = _('Mark selected invoices as overdue')

    def mark_as_cancelled(self, request, queryset):
        updated = 0
        for invoice in queryset:
            if invoice.status != InvoiceStatus.PAID:
                invoice.mark_cancelled()
                updated += 1
        self.message_user(
            request,
            _('Successfully marked %d invoices as cancelled.') % updated,
            messages.SUCCESS
        )
    mark_as_cancelled.short_description = _('Mark selected invoices as cancelled')

    def export_selected_invoices(self, request, queryset):
        self.message_user(
            request,
            _('Export functionality would be implemented here for %d invoices.') % queryset.count(),
            messages.INFO
        )
    export_selected_invoices.short_description = _('Export selected invoices')


class InvoiceStatsAdmin(admin.ModelAdmin):
    change_list_template = 'admin/invoices/invoice_stats.html'
    date_hierarchy = 'issue_date'

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
            'total_invoices': qs.count(),
            'total_amount': qs.aggregate(total=Sum('total_amount'))['total'] or 0,
            'draft_invoices': qs.filter(status=InvoiceStatus.DRAFT).count(),
            'issued_invoices': qs.filter(status=InvoiceStatus.ISSUED).count(),
            'overdue_invoices': qs.filter(status=InvoiceStatus.OVERDUE).count(),
            'paid_invoices': qs.filter(status=InvoiceStatus.PAID).count(),
            'cancelled_invoices': qs.filter(status=InvoiceStatus.CANCELLED).count(),
        }

        # Status distribution
        status_distribution = qs.values('status').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        ).order_by('status')

        monthly_summary = qs.extra({
            'month': "date_trunc('month', issue_date)"
        }).values('month').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        ).order_by('month')

        if not isinstance(response.context_data, dict):
            response.context_data = {}

        response.context_data.update({
            'stats': stats,
            'status_distribution': status_distribution,
            'monthly_summary': monthly_summary,
            'title': _('Invoice Statistics'),
        })

        return response


admin.site.register(Invoice, InvoiceStatsAdmin)