from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from common.models import CommonModel, ItemCommonModel
from orders.enums import OrderStatuses
from orders.managers import OrderTaxManager, OrderItemManager, OrderManager, OrderStatusHistoryManager


class OrderTax(CommonModel):
    """
    OrderTax model with relation to Order to keep track of taxes applied to the order.
    """
    objects = OrderTaxManager()
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="order_taxes")
    name = models.CharField(max_length=100, help_text=_("Tax name"))
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0, help_text=_("Tax rate (0–1)"))
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.0, help_text=_("Base taxable amount"))
    amount_with_taxes = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.0,
        blank=True,
        null=True,
        help_text=_("Amount including taxes")
    )
    tax_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.0,
        help_text=_("Tax amount only (amount * rate)")
    )

    def __str__(self):
        return f"Order {self.order.id} - Tax {self.name} ({self.rate})"

    class Meta:
        db_table = "order_taxes"
        verbose_name = "Order Tax"
        verbose_name_plural = "Order Taxes"
        ordering = ["-date_created"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=["order", "is_deleted"]),
            models.Index(fields=["order", "name", "is_deleted"]),
            models.Index(fields=["order", "rate", "is_deleted"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "name"],
                name="unique_order_tax_name",
                condition=models.Q(is_deleted=False)
            ),
            models.CheckConstraint(
                check=models.Q(rate__gte=0) & models.Q(rate__lte=1),
                name="valid_order_tax_rate"
            ),
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name="valid_order_tax_amount"
            ),
            models.CheckConstraint(
                check=models.Q(amount_with_taxes__gte=0),
                name="valid_order_tax_amount_with_taxes"
            ),
        ]

    def save(self, *args, **kwargs):
        # compute tax-inclusive amount
        self.tax_value = Decimal(self.amount) * Decimal(self.rate)
        self.amount_with_taxes = self.amount + self.tax_value

        super().save(*args, **kwargs)


class OrderItem(ItemCommonModel):
    """
    OrderItem model with relation to Order to keep track of items in the order.
    """
    objects = OrderItemManager()

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="order_items")

    def __str__(self):
        return f"Order {self.order.id} - Order Item {self.id}"

    class Meta:
        db_table = "order_items"
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
        ordering = ["-date_created"]
        indexes = ItemCommonModel.Meta.indexes + [
            models.Index(fields=["order", "is_deleted"]),  # Manager pattern
            models.Index(fields=["order", "product", "is_deleted"]),  # Product's orders by status
        ]
    def is_valid(self) -> bool:
        """Check if the order item is valid according to business rules."""
        if not super().is_valid():
            return False

        # Check required fields
        required_fields = [
            self.order_id
        ]
        if not all(required_fields):
            return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """Check if order item can be safely soft-deleted"""
        if not super().can_be_deleted()[0]:
            return False, super().can_be_deleted()[1]

        order_can_be_deleted, reason = self.order.can_be_deleted()
        if not order_can_be_deleted:
            return False, reason

        return True, ""


class Order(CommonModel):
    """
    Order model with relation to ShippingClass and User.
    """
    objects = OrderManager()

    order_number = models.CharField(
        _("Order Number"),
        max_length=20,
        unique=True,
        db_index=True,
        editable=False,
        null=True,
        blank=True,
        help_text=_("Unique order identifier for customer reference")
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("User")
    )
    cart = models.ForeignKey(
        "cart.Cart",
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("Cart")
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Total Amount")
    )
    status = models.CharField(
        max_length=20,
        choices=OrderStatuses.choices,
        default=OrderStatuses.PENDING,
        db_index=True,
        verbose_name=_("Order Status"),
        help_text=_("Current order status (e.g., pending, shipped, completed)")
    )

    shipping_class = models.ForeignKey(
        "shipping.ShippingClass",
        on_delete=models.PROTECT,
        related_name="orders",
        null=True,
        blank=True,
        verbose_name=_("Shipping Class"),
        help_text=_("Shipping method selected for this order")
    )

    shipping_address = models.ForeignKey(
        "common.ShippingAddress",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("Shipping Address"),
        help_text=_("Shipping address for this order")
    )

    class Meta:
        db_table = "orders"
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ["-date_created"]
        indexes = CommonModel.Meta.indexes + [
            # Order number indexes
            models.Index(fields=['order_number']),
            models.Index(fields=['order_number', 'is_deleted']),

            models.Index(fields=['user', 'is_deleted']),
            models.Index(fields=['cart', 'is_deleted']),
            models.Index(fields=['status', 'is_deleted']),
            models.Index(fields=['total_amount', 'is_deleted']),
            models.Index(fields=['user', 'status', 'is_deleted']),
            models.Index(fields=['status', 'date_created', 'is_deleted']),
            models.Index(fields=['shipping_address', 'is_deleted', 'is_active']),

        ]


    def __str__(self):
        return f"Order #{self.order_number} - {self.user.email}"

    def generate_order_number(self):
        """Generate sequential order number: ORD-000001, ORD-000002, etc."""
        last_order = Order.objects.filter(
            order_number__startswith='ORD-'
        ).order_by('-id').first()

        if last_order and last_order.order_number:
            try:
                last_number = int(last_order.order_number.split('-')[1])
                new_number = last_number + 1
            except (IndexError, ValueError):
                new_number = 1
        else:
            new_number = 1

        return f"ORD-{new_number:06d}"

    def save(self, *args, **kwargs):
        """Override save to generate order number and calculate total."""
        is_new = self.pk is None

        if is_new:
            self.mark_pending()

        # Generate order number only for new orders
        if not self.order_number:
            self.order_number = self.generate_order_number()

            # Ensure uniqueness (extremely rare but possible collision)
            while Order.objects.filter(order_number=self.order_number).exists():
                self.order_number = self.generate_order_number()

        # Calculate total amount
        self.total_amount = self.get_order_total_amount()
        super().save(*args, **kwargs)

    def get_order_total_amount(self) -> Decimal:
            """
            Calculate the total amount for the order.
            """
            order_items_total = (
                    self.order_items.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
            )

            # Calculate shipping cost properly
            if self.shipping_class:
                order_weight = self.shipping_class.calculate_order_weight(self)
                shipping_total = self.shipping_class.calculate_shipping_cost(
                    order_total=order_items_total,
                    weight_kg=order_weight,
                    destination_country_code=self.shipping_address.country.code if self.shipping_address else None
                )
            else:
                shipping_total = Decimal('0.00')

            taxes_total = self.order_taxes.aggregate(total=Sum('tax_value'))['total'] or Decimal('0.00')

            total = order_items_total + shipping_total + taxes_total
            return total.quantize(Decimal('0.01'))

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if order can be safely soft-deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        # Check if order has been paid for
        if self.status in [OrderStatuses.PAID, OrderStatuses.COMPLETED, OrderStatuses.DELIVERED]:
            return False, "Cannot delete a paid or completed order"

        # Check order items
        if self.order_items.exists():
            for order_item in self.order_items.all():
                if hasattr(order_item, 'product'):
                    can_be_deleted, reason = order_item.product.can_be_deleted()
                    if not can_be_deleted:
                        return False, f"Cannot delete due to product: {reason}"

        # Check invoices
        invoices = self.invoices.filter(is_active=True)
        for invoice in invoices:
            if invoice.payments.exists():
                if not invoice.is_fully_paid:
                    return False, "Order has unpaid invoices"
                return False, "Order has paid invoices"

        # Check shipments
        if hasattr(self, 'shipments') and self.shipments.exists():
            return False, "Order has associated shipments"

        return True, ""

    def _is_valid_status_transition(self, old_status: str, new_status: str) -> bool:
        """Check if the status transition is valid."""
        status_order = [
            OrderStatuses.PENDING,
            OrderStatuses.UNPAID,
            OrderStatuses.PAID,
            OrderStatuses.APPROVED,
            OrderStatuses.PROCESSING,
            OrderStatuses.SHIPPED,
            OrderStatuses.DELIVERED,
            OrderStatuses.COMPLETED,
            OrderStatuses.CANCELLED,
            OrderStatuses.REFUNDED,
        ]

        # Allow status to stay the same
        if old_status == new_status:
            return True

        # Special case: can cancel from most statuses
        if new_status == OrderStatuses.CANCELLED:
            return True

        # Special case: can refund from completed/delivered
        if new_status == OrderStatuses.REFUNDED:
            return old_status in [OrderStatuses.COMPLETED, OrderStatuses.DELIVERED]

        # Otherwise, can only move forward in the status flow
        try:
            return status_order.index(new_status) > status_order.index(old_status)
        except ValueError:
            return False

    def is_digital_order(self) -> bool:
        """Check if this is a digital/online order that doesn't require shipping."""
        return all(item.product.is_digital for item in self.order_items.all() if hasattr(item, 'product'))

    def delete(self, *args, **kwargs):
        """Soft delete with status update."""
        can_delete, reason = self.can_be_deleted()
        if not can_delete:
            raise ValidationError(f"Cannot delete order: {reason}")

        self.status = OrderStatuses.CANCELLED
        self.save(update_fields=['status', 'date_updated'])
        super().delete(*args, **kwargs)

    @property
    def display_order_number(self):
        """Formatted order number for display."""
        return self.order_number

    @classmethod
    def get_by_order_number(cls, order_number):
        """Helper method to retrieve order by order number."""
        try:
            return cls.objects.get(order_number=order_number)
        except cls.DoesNotExist:
            return None

    def can_be_cancelled(self):
        """Check if order can be cancelled."""
        return self.status in [OrderStatuses.PENDING, OrderStatuses.UNPAID, OrderStatuses.APPROVED]

    def get_items_count(self):
        """Get total number of items in order."""
        return self.order_items.aggregate(total=Sum('quantity'))['total'] or 0

    def cancel(self):
        """Cancel the order."""
        if not self.can_be_cancelled():
            raise ValidationError("Order cannot be cancelled.")

        self._is_valid_status_transition(self.status, OrderStatuses.CANCELLED)

        self.status = OrderStatuses.CANCELLED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_completed(self):
        """Mark the order as completed."""
        self._is_valid_status_transition(self.status, OrderStatuses.COMPLETED)

        self.status = OrderStatuses.COMPLETED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_delivered(self):
        """Mark the order as delivered."""
        self._is_valid_status_transition(self.status, OrderStatuses.DELIVERED)

        self.status = OrderStatuses.DELIVERED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_paid(self):
        """Mark the order as paid."""
        self._is_valid_status_transition(self.status, OrderStatuses.PAID)

        self.status = OrderStatuses.PAID
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_unpaid(self):
        """Mark the order as unpaid."""
        self._is_valid_status_transition(self.status, OrderStatuses.UNPAID)

        self.status = OrderStatuses.UNPAID
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_approved(self):
        """Mark the order as approved."""
        self._is_valid_status_transition(self.status, OrderStatuses.APPROVED)

        self.status = OrderStatuses.APPROVED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_processing(self):
        """Mark the order as processing."""
        self._is_valid_status_transition(self.status, OrderStatuses.PROCESSING)

        self.status = OrderStatuses.PROCESSING
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_shipped(self):
        """Mark the order as shipped."""
        self._is_valid_status_transition(self.status, OrderStatuses.SHIPPED)

        self.status = OrderStatuses.SHIPPED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_pending(self):
        """Mark the order as pending."""
        self._is_valid_status_transition(self.status, OrderStatuses.PENDING)

        self.status = OrderStatuses.PENDING
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

class OrderStatusHistory(CommonModel):
    objects = OrderStatusHistoryManager()

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="order_status_history")
    status = models.CharField(max_length=20, choices=OrderStatuses.choices, db_index=True)

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Status Change Notes"),
        help_text=_("Optional notes about why status changed")
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Changed By"),
        help_text=_("User who changed the order status")
    )

    class Meta:
        db_table = "order_status_history"
        verbose_name = "Order Status History"
        verbose_name_plural = "Order Status Histories"
        ordering = ["-date_created"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=["order", "is_deleted"]),
            models.Index(fields=["order", "status", "is_deleted"]),
            models.Index(fields=['status', 'date_created', 'is_deleted']),  # Admin filtering by status/time
            models.Index(fields=['changed_by', 'date_created', 'is_deleted']),
        ]


    def __str__(self):
        return f"Order {self.order.order_number} - {self.status} at {self.date_created}"

