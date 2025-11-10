from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

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

    def delete(self, *args, **kwargs):
        """Soft delete with status update."""
        self.status = OrderStatuses.CANCELLED
        super().delete(*args, **kwargs)

    @property
    def display_order_number(self):
        """Formatted order number for display."""
        return self.order_number

    @classmethod
    def get_by_order_number(cls, order_number):
        """Helper method to retrieve order by order number."""
        try:
            return cls.objects.get(order_number=order_number, is_deleted=False)
        except cls.DoesNotExist:
            return None

    def can_be_cancelled(self):
        """Check if order can be cancelled."""
        return self.status in [OrderStatuses.PENDING, OrderStatuses.UNPAID, OrderStatuses.APPROVED]

    def get_items_count(self):
        """Get total number of items in order."""
        return self.order_items.aggregate(total=Sum('quantity'))['total'] or 0


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

