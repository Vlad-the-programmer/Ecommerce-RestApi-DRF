from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from common.managers import SoftDeleteManager
from refunds.enums import RefundStatus, ACTIVE_REFUND_STATUSES


class RefundManager(SoftDeleteManager):
    """
    Custom manager for Refund model with essential refund methods.
    """

    def active(self):
        return super().active().filter(status_in=ACTIVE_REFUND_STATUSES)

    def only_deleted(self):
        return super().only_deleted().filter(
            status_in=[
                RefundStatus.REJECTED,
                RefundStatus.CANCELLED,
                RefundStatus.COMPLETED,
            ]
        )

    def pending(self):
        return self.get_queryset().filter(status=RefundStatus.PENDING)

    def approved(self):
        return self.get_queryset().filter(status=RefundStatus.APPROVED)

    def completed(self):
        return self.get_queryset().filter(status=RefundStatus.COMPLETED)

    def rejected(self):
        return self.get_queryset().filter(status=RefundStatus.REJECTED)

    def for_order(self, order):
        return self.get_queryset().filter(order=order)

    def for_customer(self, customer):
        return self.get_queryset().filter(customer=customer)

    def for_payment(self, payment):
        return self.get_queryset().filter(payment=payment)

    def recent(self, days=30):
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.get_queryset().filter(requested_at__gte=cutoff_date)

    def pending_approval(self):
        """Get refunds pending approval"""
        return self.pending().order_by('requested_at')

    def total_refunded_amount(self):
        result = self.completed().aggregate(total=Sum('amount_refunded'))
        return result['total'] or Decimal('0.00')


class RefundItemManager(SoftDeleteManager):
    """
    Manager for RefundItem model.
    """

    def only_deleted(self):
        return super().only_deleted().filter(
            refund_status_in=[
                RefundStatus.REJECTED,
                RefundStatus.CANCELLED,
                RefundStatus.COMPLETED,
            ]
        )

    def active(self):
        return super().active().filter(refund_status_in=ACTIVE_REFUND_STATUSES)

    def for_refund(self, refund):
        return self.get_queryset().filter(refund=refund)

    def for_order_item(self, order_item):
        return self.get_queryset().filter(order_item=order_item)