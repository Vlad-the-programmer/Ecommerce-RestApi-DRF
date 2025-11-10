from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from common.managers import SoftDeleteManager


class OrderManager(SoftDeleteManager):
    """
    Custom manager for Order model with order-specific methods.
    """

    # Status-based filters
    def pending(self):
        from .enums import OrderStatuses
        return self.get_queryset().filter(status=OrderStatuses.PENDING)

    def completed(self):
        from .enums import OrderStatuses
        return self.get_queryset().filter(status=OrderStatuses.COMPLETED)

    def cancelled(self):
        from .enums import OrderStatuses
        return self.get_queryset().filter(status=OrderStatuses.CANCELLED)

    def refunded(self):
        from .enums import OrderStatuses
        return self.get_queryset().filter(status=OrderStatuses.REFUNDED)

    def shipped(self):
        from .enums import OrderStatuses
        return self.get_queryset().filter(status=OrderStatuses.SHIPPED)

    def delivered(self):
        from .enums import OrderStatuses
        return self.get_queryset().filter(status=OrderStatuses.DELIVERED)

    def paid(self):
        from .enums import OrderStatuses
        return self.get_queryset().filter(status=OrderStatuses.PAID)

    def unpaid(self):
        from .enums import OrderStatuses
        return self.get_queryset().filter(status=OrderStatuses.UNPAID)

    def approved(self):
        from .enums import OrderStatuses
        return self.get_queryset().filter(status=OrderStatuses.APPROVED)

    # User and cart related
    def for_user(self, user):
        return self.get_queryset().filter(user=user)

    def for_cart(self, cart):
        return self.get_queryset().filter(cart=cart)

    def by_order_number(self, order_number):
        return self.get_queryset().filter(order_number=order_number).first()

    # Date-based queries
    def recent(self, days=30):
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.get_queryset().filter(date_created__gte=cutoff_date)

    def today(self):
        today = timezone.now().date()
        return self.get_queryset().filter(date_created__date=today)

    # Analytics
    def total_revenue(self):
        result = self.get_queryset().aggregate(total=Sum('total_amount'))
        return result['total'] or Decimal('0.00')

    def with_items_count(self):
        return self.get_queryset().annotate(
            items_count=Count('order_items', filter=Q(order_items__is_deleted=False))
        )


class OrderItemManager(SoftDeleteManager):
    """
    Manager for OrderItem model.
    """

    def for_order(self, order):
        return self.get_queryset().filter(order=order)

    def for_product(self, product):
        return self.get_queryset().filter(product=product)

    def with_product_details(self):
        return self.get_queryset().select_related('product', 'variant')


class OrderTaxManager(SoftDeleteManager):
    """
    Manager for OrderTax model.
    """

    def for_order(self, order):
        return self.get_queryset().filter(order=order)

    def by_tax_name(self, name):
        return self.get_queryset().filter(name=name)


class OrderStatusHistoryManager(SoftDeleteManager):
    """
    Manager for OrderStatusHistory model.
    """
    def for_order(self, order):
        return self.get_queryset().filter(order=order).order_by('-date_created')

    def by_status(self, status):
        return self.get_queryset().filter(status=status)

    def recent_changes(self, days=7):
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.get_queryset().filter(date_created__gte=cutoff_date)