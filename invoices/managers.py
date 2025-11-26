from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from common.managers import SoftDeleteManager
from invoices.enums import InvoiceStatus


class InvoiceManager(SoftDeleteManager):
    """
    Custom manager for Invoice model with essential invoice methods.
    """
    def draft(self):
        from .enums import InvoiceStatus
        return self.get_queryset().filter(status=InvoiceStatus.DRAFT)

    def issued(self):
        from .enums import InvoiceStatus
        return self.get_queryset().filter(status=InvoiceStatus.ISSUED)

    def paid(self):
        from .enums import InvoiceStatus
        return self.get_queryset().filter(status=InvoiceStatus.PAID)

    def overdue(self):
        from .enums import InvoiceStatus
        return self.get_queryset().filter(status=InvoiceStatus.OVERDUE)

    def cancelled(self):
        from .enums import InvoiceStatus
        return self.get_queryset().filter(status=InvoiceStatus.CANCELLED)

    # User and reference filters
    def for_user(self, user):
        return self.get_queryset().filter(user=user)

    def by_invoice_number(self, invoice_number):
        return self.get_queryset().filter(invoice_number=invoice_number).first()

    # Date-based queries
    def due_soon(self, days=7):
        """Get invoices due within specified days"""
        target_date = timezone.now().date() + timedelta(days=days)
        return self.get_queryset().filter(
            due_date__lte=target_date,
            status__in=[InvoiceStatus.DRAFT, InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE]
        )

    def overdue_invoices(self):
        """Get currently overdue invoices"""
        today = timezone.now().date()
        return self.get_queryset().filter(
            due_date__lt=today,
            status__in=[InvoiceStatus.DRAFT, InvoiceStatus.ISSUED]
        )

    # Analytics
    def total_outstanding(self):
        """Calculate total outstanding amount"""
        result = self.get_queryset().filter(
            status__in=[InvoiceStatus.DRAFT, InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE]
        ).aggregate(total=Sum('total_amount'))
        return result['total'] or Decimal('0.00')

    def get_by_status(self):
        """Get count of invoices by status"""
        from django.db.models import Count
        return self.get_queryset().values('status').annotate(
            count=Count('id'),
            total_amount=Sum('total_amount')
        )