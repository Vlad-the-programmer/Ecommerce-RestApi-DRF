import logging
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from common.models import CommonModel, ItemCommonModel
from orders.enums import OrderStatuses
from orders.managers import OrderTaxManager, OrderItemManager, OrderManager, OrderStatusHistoryManager

logger = logging.getLogger(__name__)


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

    def is_valid(self, *args, **kwargs) -> bool:
        """Check if the order tax is valid.
        
        Returns:
            bool: True if the order tax is valid, False otherwise.
        """
        # Check parent class validation
        if not super().is_valid():
            logger.warning(f"Order tax {self.id} failed basic model validation")
            return False
            
        # Check if order exists and is valid
        if not hasattr(self, 'order') or not self.order or self.order.is_deleted:
            logger.debug(f"Order for this tax does not exist ({not hasattr(self, 'order')} \
                            or is deleted -> ({self.order.is_deleted})")
            return False
            
        # Check if amount is valid
        if self.amount < 0:
            logger.debug(f"Order Tax failed. Order Tax amount is < 0")
            return False
            
        # Check if rate is within valid range (0-1)
        if not (0 <= float(self.rate) <= 1):
            logger.debug(f"Order Tax failed. Order Tax rate is not within valid range (0-1)")
            return False
            
        # Check if tax_value is correctly calculated
        expected_tax = Decimal(str(self.amount)) * Decimal(str(self.rate))
        if abs(float(self.tax_value) - float(expected_tax)) > 0.01:  # Allow for small floating point differences
            message = (
                    f"Order Tax failed. Order Tax tax_value is not correctly calculated"
                    f"abs(float(self.tax_value) - float(expected_tax)) > 0.01 is False"
            )
            logger.debug(message)
            return False
            
        # Check if amount_with_taxes is correctly calculated
        expected_total = self.amount + self.tax_value
        if abs(float(self.amount_with_taxes) - float(expected_total)) > 0.01:
            message = (
                    f"Order Tax failed. Order Tax amount_with_taxes is not correctly calculated"
                    f"abs(float(self.amount_with_taxes) - float(expected_total)) > 0.01 is False"
            )
            logger.debug(message)
            return False
            
        return True
        
    def can_be_deleted(self) -> tuple[bool, str]:
        """Check if the order tax can be safely deleted.
        
        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        # Check parent class validation
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason
            
        # Check if order exists and is in a state that allows tax deletion
        if not hasattr(self, 'order') or not self.order:
            return True, ""

        from orders.enums import active_order_statuses

        # Prevent deletion if order is not in a draft or pending state
        if self.order.status not in active_order_statuses:
            return False, f"Cannot delete tax from an active order with status {self.order.status_display}"
            
        return True, ""
        
    def save(self, *args, **kwargs):
        # compute tax-inclusive amount
        self.tax_value = Decimal(str(self.amount)) * Decimal(str(self.rate))
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
    def is_valid(self, *args, **kwargs) -> bool:
        """Check if the order item is valid according to business rules.
        
        Validates:
        1. Parent class validation (is_active, is_deleted, etc.)
        2. Order exists and is valid
        3. Product or variant exists and is valid
        4. Quantity is valid
        5. Total price is correctly calculated
        
        Returns:
            bool: True if the order item is valid, False otherwise.
        """
        # Check parent class validation
        if not super().is_valid():
            return False
            
        # Check if order exists and is valid
        if not hasattr(self, 'order') or not self.order or self.order.is_deleted:
            return False
            
        # Check if either product or variant exists
        if not self.product_id and not self.variant_id:
            return False
            
        # Check if variant belongs to product (if both are specified)
        if self.product_id and self.variant_id and self.variant.product_id != self.product_id:
            return False
            
        # Check if quantity is valid
        if self.quantity < 1:
            return False
            
        # Check if total price is valid
        if self.total_price < 0:
            return False
            
        # If this is an update, check if the order is in a state that allows item modifications
        if self.pk and self.order.status not in [OrderStatuses.PENDING, OrderStatuses.DRAFT]:
            return False
            
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """Check if the order item can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
                - can_delete: True if the order item can be deleted, False otherwise
                - reason: Empty string if can_delete is True, otherwise the reason why it can't be deleted
        """
        # Check parent class validation
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        # Check if order exists and is in a state that allows item deletion
        if not hasattr(self, 'order') or not self.order:
            return True, ""

        # Prevent deletion if order is not in a draft or pending state
        if self.order.status not in [OrderStatuses.DRAFT, OrderStatuses.PENDING]:
            return False, "Cannot delete items from an order that is not in draft or pending status"

        # Check if there are any associated shipments
        if hasattr(self, 'shipment_items') and self.shipment_items.exists():
            return False, "Cannot delete order item that has been shipped"

        # Check if there are any associated refunds
        if hasattr(self, 'refund_items') and self.refund_items.exists():
            return False, "Cannot delete order item that has refunds"

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
        constraints = [
            # Ensure total_amount is non-negative
            models.CheckConstraint(
                check=models.Q(total_amount__gte=0),
                name='%(app_label)s_%(class)s_positive_total_amount',
                violation_error_message='Total amount cannot be negative.'
            ),
            # Ensure order_number is unique and not empty when not null
            models.UniqueConstraint(
                fields=['order_number'],
                name='%(app_label)s_%(class)s_unique_order_number',
                condition=models.Q(order_number__isnull=False),
                violation_error_message='Order number must be unique.'
            ),
            # Ensure order has a shipping address if it's not a digital order
            models.CheckConstraint(
                check=(
                        models.Q(is_digital_order=True) |
                        models.Q(shipping_address__isnull=False)
                ),
                name='%(app_label)s_%(class)s_shipping_address_required',
                violation_error_message='Shipping address is required for non-digital orders.'
            ),
            # Ensure order has at least one item
            models.CheckConstraint(
                check=models.Exists(
                    OrderItem.objects.filter(
                        order_id=models.OuterRef('pk'),
                        is_deleted=False
                    )
                ),
                name='%(app_label)s_%(class)s_has_items',
                violation_error_message='Order must have at least one item.'
            ),
            # Prevent modifying completed/cancelled orders
            models.CheckConstraint(
                check=~models.Q(status__in=[
                    OrderStatuses.COMPLETED,
                    OrderStatuses.CANCELLED,
                    OrderStatuses.REFUNDED
                ]) | models.Q(
                    models.Q(status__in=[
                        OrderStatuses.COMPLETED,
                        OrderStatuses.CANCELLED,
                        OrderStatuses.REFUNDED
                    ]) & models.Q(
                        is_deleted=False,
                        is_active=True
                    )
                ),
                name='%(app_label)s_%(class)s_protect_completed_orders',
                violation_error_message='Completed, cancelled, or refunded orders cannot be modified.'
            )
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
        is_new = self._state.adding

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

    def delete(self, *args, **kwargs):
        """Soft delete with status update."""
        can_delete, reason = self.can_be_deleted()
        if not can_delete:
            logger.warning(f"Cannot delete order: {reason}")
            raise ValidationError(f"Cannot delete order: {reason}")

        self.status = OrderStatuses.CANCELLED
        self.save(update_fields=['status', 'date_updated'])
        super().delete(*args, **kwargs)

    def is_valid(self, *args, **kwargs) -> bool:
        """Check if the order is valid according to business rules.

        Validates:
        1. Parent class validation (is_active, is_deleted, etc.)
        2. Required fields are present
        3. Order number format is valid
        4. Total amount is non-negative
        5. Shipping address is valid (if required)
        6. Order items are valid
        7. Order taxes are valid
        8. Status transition is valid (if status is being changed)

        Returns:
            bool: True if the order is valid, False otherwise
        """
        # Check parent class validation
        if not super().is_valid():
            return False

        # Check required fields
        required_fields = {
            'order_number': self.order_number,
            'user': self.user,
            'cart': self.cart,
            'total_amount': self.total_amount is not None,
            'status': self.status,
        }

        for field, value in required_fields.items():
            if not value:
                logger.warning(f"Order validation failed: Missing required field {field}")
                return False

        # Validate order number format
        if not (isinstance(self.order_number, str) and
                len(self.order_number) > 0 and
                self.order_number.startswith('ORD-')):
            logger.warning(f"Order validation failed: Invalid order number format: {self.order_number}")
            return False

        # Validate total amount
        if self.total_amount < Decimal('0.00'):
            logger.warning(f"Order validation failed: Total amount cannot be negative: {self.total_amount}")
            return False

        # Validate shipping requirements
        if not self.is_digital_order() and not self.shipping_address:
            logger.warning("Order validation failed: Shipping address is required for non-digital orders")
            return False

        if self.shipping_address and not self.shipping_address.is_valid():
            logger.warning("Order validation failed: Invalid shipping address")
            return False

        # Validate order items
        if not hasattr(self, 'order_items') or not self.order_items.exists():
            logger.warning("Order validation failed: Order must have at least one item")
            return False

        for item in self.order_items.all():
            if not item.is_valid():
                logger.warning(f"Order validation failed: Invalid order item {item.id}")
                return False

        # Validate order taxes
        if hasattr(self, 'order_taxes'):
            for tax in self.order_taxes.all():
                if not tax.is_valid():
                    logger.warning(f"Order validation failed: Invalid order tax {tax.id}")
                    return False

        # Validate status transition if this is an update
        if self.pk:
            try:
                old_status = Order.objects.get(pk=self.pk).status
                if old_status != self.status and not self._is_valid_status_transition(old_status, self.status):
                    logger.warning(f"Order validation failed: Invalid status transition from {old_status} to {self.status}")
                    return False
            except Order.DoesNotExist:
                logger.warning("Order validation failed: Order does not exist")
                return False

        return True

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

        from orders.enums import active_order_statuses

        # Check if order has been paid for
        if self.status in active_order_statuses and self.is_active:
            return False, "Cannot delete an active order"

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

    @property
    def display_order_number(self):
        """Formatted order number for display."""
        return self.order_number

    @property
    def status_display(self):
        """Get the display name of the order status."""
        return dict(OrderStatuses.choices).get(self.status, self.status)

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
        constraints = [
        # Ensure status is a valid choice
        models.CheckConstraint(
            check=models.Q(status__in=dict(OrderStatuses.choices).keys()),
            name='%(app_label)s_%(class)s_valid_status',
            violation_error_message=_('Invalid status value.')
        ),
        # Prevent duplicate status transitions at the same time
        models.UniqueConstraint(
            fields=['order', 'status', 'date_created'],
            name='%(app_label)s_%(class)s_unique_status_per_timestamp',
            violation_error_message=_('Duplicate status change detected.')
        )
    ]

    def __str__(self):
        return f"Order {self.order.order_number} - {self.get_status_display()} at {self.date_created}"

    def is_valid(self, *args, **kwargs) -> bool:
        """
        Check if the status history record is valid.

        Validates:
        1. Parent class validation (is_active, is_deleted, etc.)
        2. Order exists and is valid
        3. Status is a valid choice
        4. Status transition is valid for the order
        5. Changed_by user exists (if provided)

        Returns:
            bool: True if the status history record is valid, False otherwise
        """
        # Check parent class validation
        if not super().is_valid():
            logger.warning("OrderStatusHistory validation failed: Parent class validation failed")
            return False

        # Check required fields
        required_fields = {
            'order': self.order_id,
            'status': self.status
        }

        for field, value in required_fields.items():
            if not value:
                logger.warning(f"OrderStatusHistory validation failed: Missing required field {field}")
                return False

        # Validate status is a valid choice
        if self.status not in dict(OrderStatuses.choices):
            logger.warning(f"OrderStatusHistory validation failed: Invalid status {self.status}")
            return False

        # If this is an update, check if the status is being changed
        if self.pk:
            try:
                old_status = OrderStatusHistory.objects.get(pk=self.pk).status
                if old_status != self.status:
                    logger.warning(
                        "OrderStatusHistory validation failed: Cannot change status of existing history record")
                    return False
            except OrderStatusHistory.DoesNotExist:
                pass

        # If changed_by is provided, check the user exists
        if self.changed_by_id and not hasattr(self, 'changed_by'):
            logger.warning("OrderStatusHistory validation failed: Invalid changed_by user")
            return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the status history record can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
                - can_delete: True if the record can be deleted, False otherwise
                - reason: Empty string if can_delete is True, otherwise the reason why it can't be deleted
        """
        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        # Prevent deletion of the most recent status history for an order
        try:
            latest_status = OrderStatusHistory.objects.filter(
                order_id=self.order_id,
                is_deleted=False
            ).latest('date_created')

            if self.pk == latest_status.pk:
                return False, "Cannot delete the most recent status history record"

        except OrderStatusHistory.DoesNotExist:
            pass

        # Check if this status is currently active on the order
        if hasattr(self, 'order') and self.order.status == self.status:
            return False, f"Cannot delete active status history for order {self.order.order_number}"

        return True, ""


