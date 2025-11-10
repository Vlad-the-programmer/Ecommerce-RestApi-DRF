from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from common.managers import SoftDeleteManager


class RefundManager(SoftDeleteManager):
    """
    Custom manager for Refund model with essential refund methods.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def with_deleted(self):
        return super().get_queryset()

    def only_deleted(self):
        return super().get_queryset().filter(is_deleted=True)

    def get(self, *args, **kwargs):
        return self.get_queryset().get(*args, **kwargs)

    # Status-based filters
    def pending(self):
        from .enums import RefundStatus
        return self.get_queryset().filter(status=RefundStatus.PENDING)

    def approved(self):
        from .enums import RefundStatus
        return self.get_queryset().filter(status=RefundStatus.APPROVED)

    def completed(self):
        from .enums import RefundStatus
        return self.get_queryset().filter(status=RefundStatus.COMPLETED)

    def rejected(self):
        from .enums import RefundStatus
        return self.get_queryset().filter(status=RefundStatus.REJECTED)

    # Related object filters
    def for_order(self, order):
        return self.get_queryset().filter(order=order)

    def for_customer(self, customer):
        return self.get_queryset().filter(customer=customer)

    def for_payment(self, payment):
        return self.get_queryset().filter(payment=payment)

    # Date-based queries
    def recent(self, days=30):
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.get_queryset().filter(requested_at__gte=cutoff_date)

    def pending_approval(self):
        """Get refunds pending approval"""
        return self.pending().order_by('requested_at')

    # Analytics
    def total_refunded_amount(self):
        result = self.completed().aggregate(total=Sum('amount_refunded'))
        return result['total'] or Decimal('0.00')


class RefundItemManager(SoftDeleteManager):
    """
    Manager for RefundItem model.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def for_refund(self, refund):
        return self.get_queryset().filter(refund=refund)

    def for_order_item(self, order_item):
        return self.get_queryset().filter(order_item=order_item)