from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel, ItemCommonModel
from orders.enums import OrderStatuses
from shipping.models import ShippingClass

class OrderTax(CommonModel):
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="order_taxes")
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
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="order_items")

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
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name=_("User")
    )
    cart = models.ForeignKey(
        "cart.Cart",
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name=_("Cart")
    )
    shipping_class = models.ForeignKey(
        ShippingClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("Shipping Class")
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Total Amount")
    )
    shipping_address = models.ForeignKey(
        "users.ShippingAddress",
        on_delete=models.SET_NULL,
        related_name="orders",
        verbose_name=_("Shipping Address")
    )
    status = models.CharField(
        max_length = 20,
        choices = OrderStatuses.choices,
        default = OrderStatuses.PENDING,
        db_index = True,
        verbose_name=_("Order Status"),
        help_text=_("Current order status (e.g., pending, shipped, completed)")
    )

    class Meta:
        db_table = "orders"
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ["-date_created"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=['user', 'is_deleted']),
            models.Index(fields=['cart', 'is_deleted']),
            models.Index(fields=['shipping_class', 'is_deleted']),
            models.Index(fields=['status', 'is_deleted']),
            models.Index(fields=['total_amount', 'is_deleted']),

            models.Index(fields=['user', 'status', 'is_deleted']),  # User dashboard lookups
            models.Index(fields=['status', 'date_created', 'is_deleted']),  # Admin filtering by status/time
        ]

    def __str__(self):
        return f"Order #{self.pk} - {self.user}"

    def delete(self, *args, **kwargs):
        self.status = OrderStatuses.CANCELLED
        super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        self.total_amount = self.get_order_total_amount()
        super().save(*args, **kwargs)

    def get_order_total_amount(self) -> Decimal:
        """
        Calculate the total amount for the order:
        - Sum of order items (total_price)
        - Plus shipping cost
        - Plus taxes
        """
        # Safely get all components
        order_items_total = (
                self.order_items.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
        )
        shipping_total = (
            self.shipping_class.calculate_shipping_cost() if self.shipping_class else Decimal('0.00')
        )
        taxes_total = self.order_taxes.aggregate(total=Sum('tax_value'))['total'] or Decimal('0.00')
        total = order_items_total + shipping_total + taxes_total
        return total.quantize(Decimal('0.01'))

