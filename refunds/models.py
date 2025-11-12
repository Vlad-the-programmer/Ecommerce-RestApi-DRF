from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal

from rest_framework.exceptions import ValidationError

from common.models import CommonModel
from refunds.enums import RefundStatus, RefundReason, RefundMethod
from refunds.managers import RefundManager, RefundItemManager


class Refund(CommonModel):
    """
    Refund model for handling order refunds with proper normalization.
    Supports partial refunds and multiple refund reasons.
    """
    objects = RefundManager()

    refund_number = models.CharField(
        _('Refund Number'),
        max_length=20,
        unique=True,
        db_index=True,
        help_text=_('Unique identifier for the refund')
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name='refunds',
        verbose_name=_('Order'),
        help_text=_('Order being refunded')
    )
    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.PROTECT,
        related_name='refunds',
        verbose_name=_('Payment'),
        help_text=_('Original payment being refunded')
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='refunds',
        verbose_name=_('Customer'),
        help_text=_('Customer receiving the refund')
    )

    # Refund details
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING,
        db_index=True,
        help_text=_('Current status of the refund')
    )
    reason = models.CharField(
        _('Reason'),
        max_length=50,
        choices=RefundReason.choices,
        help_text=_('Reason for the refund')
    )
    reason_description = models.TextField(
        _('Reason Description'),
        blank=True,
        null=True,
        help_text=_('Detailed description of the refund reason')
    )
    refund_method = models.CharField(
        _('Refund Method'),
        max_length=20,
        choices=RefundMethod.choices,
        default=RefundMethod.ORIGINAL_PAYMENT,
        help_text=_('Method used to process the refund')
    )

    # Financial details
    amount_requested = models.DecimalField(
        _('Amount Requested'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text=_('Amount requested for refund')
    )
    amount_approved = models.DecimalField(
        _('Amount Approved'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        null=True,
        blank=True,
        help_text=_('Amount approved for refund')
    )
    amount_refunded = models.DecimalField(
        _('Amount Refunded'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        default=Decimal('0.00'),
        help_text=_('Amount actually refunded to customer')
    )

    # Processing details
    requested_at = models.DateTimeField(
        _('Requested At'),
        auto_now_add=True,
        help_text=_('When the refund was requested')
    )
    processed_at = models.DateTimeField(
        _('Processed At'),
        null=True,
        blank=True,
        help_text=_('When the refund was processed')
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_refunds',
        verbose_name=_('Processed By'),
        help_text=_('Staff member who processed the refund')
    )

    # Additional metadata
    customer_notes = models.TextField(
        _('Customer Notes'),
        blank=True,
        null=True,
        help_text=_('Additional notes from the customer')
    )
    internal_notes = models.TextField(
        _('Internal Notes'),
        blank=True,
        null=True,
        help_text=_('Internal notes for staff')
    )
    refund_receipt = models.FileField(
        _('Refund Receipt'),
        upload_to='refunds/receipts/',
        null=True,
        blank=True,
        help_text=_('Refund receipt document')
    )

    class Meta:
        db_table = 'refunds'
        verbose_name = _('Refund')
        verbose_name_plural = _('Refunds')
        ordering = ['-requested_at']

        constraints = [
            # Ensure valid amount relationships
            models.CheckConstraint(
                check=models.Q(amount_approved__lte=models.F('amount_requested')),
                name='approved_amount_lte_requested'
            ),
            models.CheckConstraint(
                check=models.Q(amount_refunded__lte=models.F('amount_approved')),
                name='refunded_amount_lte_approved'
            ),
            # Prevent duplicate pending refunds for same order
            models.UniqueConstraint(
                fields=['order', 'status'],
                condition=models.Q(status__in=['pending', 'processing']),
                name='unique_pending_refund_per_order'
            ),
        ]
        indexes = [
            # Core query patterns
            models.Index(fields=['refund_number']),
            models.Index(fields=['status', 'is_deleted']),
            models.Index(fields=['order', 'status']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['payment', 'status']),
            models.Index(fields=['refund_number', 'is_deleted']),
            models.Index(fields=['status', 'is_deleted', 'requested_at']),
            models.Index(fields=['customer', 'is_deleted', 'requested_at']),

            # Date-based queries
            models.Index(fields=['requested_at', 'status']),
            models.Index(fields=['processed_at', 'status']),
            models.Index(fields=['requested_at', 'customer']),
            models.Index(fields=['is_deleted', 'status', 'requested_at']),
            models.Index(fields=['refund_method', 'is_deleted', 'status']),

            # Financial reporting
            models.Index(fields=['status', 'amount_requested']),
            models.Index(fields=['refund_method', 'status']),

            # Combined status and business logic
            models.Index(fields=['is_active', 'is_deleted', 'status']),
            models.Index(fields=['reason', 'status', 'is_deleted']),
        ]

    def __str__(self):
        return f"Refund #{self.refund_number} - {self.order.order_number}"

    def is_valid(self) -> bool:
        """
        Check if the refund is valid according to business rules.

        Returns:
            bool: True if refund is valid, False otherwise
        """
        if not super().is_valid():
            return False

        # Check required fields
        required_fields = [
            self.refund_number,
            self.order_id,
            self.payment_id,
            self.customer_id,
            self.status in dict(RefundStatus.choices),
            self.reason in dict(RefundReason.choices),
            self.refund_method in dict(RefundMethod.choices),
            self.amount_requested is not None,
            self.requested_at is not None
        ]

        if not all(required_fields):
            return False

        # Amount validations
        if self.amount_requested <= 0:
            return False

        if self.amount_approved is not None and self.amount_approved < 0:
            return False

        if self.amount_refunded < 0:
            return False

        # Amount relationship validations
        if self.amount_approved is not None and self.amount_approved > self.amount_requested:
            return False

        if self.amount_refunded > 0 and (self.amount_approved is None or self.amount_refunded > self.amount_approved):
            return False

        # Status-specific validations
        if self.status == RefundStatus.COMPLETED:
            if not self.processed_at:
                return False
            if self.amount_refunded <= 0:
                return False
            if self.amount_approved is None or self.amount_approved <= 0:
                return False

        # Date validations
        if self.processed_at and self.processed_at < self.requested_at:
            return False

        # Check if order exists and is not deleted
        if hasattr(self, 'order') and self.order.is_deleted:
            return False

        # Check if payment exists and is not deleted
        if hasattr(self, 'payment') and (self.payment.is_deleted or not self.payment.is_successful):
            return False

        # Check if customer exists and is active
        if hasattr(self, 'customer') and not self.customer.is_active:
            return False

        # Check refund items if they exist
        if hasattr(self, 'items'):
            total_items_amount = sum(item.total_amount for item in self.items.all())
            if abs(total_items_amount - self.amount_requested) > Decimal(
                    '0.01'):  # Allow for small rounding differences
                return False

        return True

    def save(self, *args, **kwargs):
        """Override save to generate refund number and handle status transitions."""
        is_new = self._state.adding

        if is_new and not self.refund_number:
            self.refund_number = self.generate_refund_number()

        # Update processed_at when status changes to completed
        if self.status == RefundStatus.COMPLETED and not self.processed_at:
            self.processed_at = timezone.now()

        super().save(*args, **kwargs)

    def can_be_deleted(self) -> tuple[bool, str]:
        """Check if refund can be safely soft-deleted."""
        if not super().can_be_deleted()[0]:
            return False, super().can_be_deleted()[1]

        if self.is_completed:
            return False, "Completed refunds should never be deleted"
        if self.amount_refunded > 0:
            return False, "Refunds with actual money movement can't be deleted"
        if self.status != RefundStatus.CANCELLED:
            self.status = RefundStatus.CANCELLED
            return False, "Refund must be cancelled before deletion"
        return True, ""

    def generate_refund_number(self):
        """Generate unique refund number."""
        import random
        import string
        return f"REF-{timezone.now().strftime('%Y%m%d')}- \
                {''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"

    @property
    def is_full_refund(self):
        """Check if this is a full refund of the order."""
        return self.amount_requested >= self.order.total_amount

    @property
    def can_be_processed(self):
        """Check if refund can be processed."""
        return self.status in [RefundStatus.PENDING, RefundStatus.APPROVED]

    @property
    def is_completed(self):
        return self.status == RefundStatus.COMPLETED

    def _validate_status_transition(self, old_status: str, new_status: str) -> None:
        """Validate status transitions."""
        status_order = [
            RefundStatus.PENDING,
            RefundStatus.APPROVED,
            RefundStatus.COMPLETED,
            RefundStatus.REJECTED,
            RefundStatus.CANCELLED,
        ]

        if old_status == new_status:
            return

        if old_status == RefundStatus.CANCELLED:
            raise ValidationError(_("Cannot change status of a cancelled refund."))

        if old_status == RefundStatus.COMPLETED and new_status != RefundStatus.CANCELLED:
            raise ValidationError(_("Cannot modify a completed refund."))

        if old_status == RefundStatus.REJECTED and new_status != RefundStatus.CANCELLED:
            raise ValidationError(_("Cannot modify a rejected refund."))

        if (status_order.index(new_status) < status_order.index(old_status) and
                new_status != RefundStatus.CANCELLED and
                new_status != RefundStatus.REJECTED and
                new_status != RefundStatus.COMPLETED):
            raise ValidationError(_("Cannot move to a previous status."))

    def approve(self, approved_amount=None, processed_by=None):
        """Approve the refund request."""
        if self.status != RefundStatus.PENDING:
            raise ValidationError(_('Only pending refunds can be approved.'))
        self._validate_status_transition(self.status, RefundStatus.APPROVED)

        self.status = RefundStatus.APPROVED
        self.is_active = False
        self.amount_approved = approved_amount or self.amount_requested
        self.processed_by = processed_by
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "is_active", "date_updated", "amount_approved", "processed_by", "processed_at"])

    def complete(self, refunded_amount=None, processed_by=None):
        """Mark refund as completed."""
        if self.status != RefundStatus.APPROVED:
            raise ValidationError(_('Only approved refunds can be completed.'))

        self._validate_status_transition(self.status, RefundStatus.COMPLETED)

        self.status = RefundStatus.COMPLETED

        self.is_active = False
        self.amount_refunded = refunded_amount or self.amount_approved
        self.payment.refund(self.amount_refunded, self.reason, self.refund_method) # Send a refund request to the payment processor
        self.processed_at = timezone.now()
        self.processed_by = processed_by
        self.save(update_fields=["status", "is_active", "date_updated", "amount_refunded", "processed_at", "payment", "processed_by"])

    def reject(self, processed_by=None, notes=None):
        """Reject the refund request."""
        if self.status != RefundStatus.PENDING:
            raise ValidationError(_('Only pending refunds can be rejected.'))

        self._validate_status_transition(self.status, RefundStatus.REJECTED)

        self.status = RefundStatus.REJECTED
        self.is_active = False
        self.processed_by = processed_by
        self.processed_at = timezone.now()

        update_fields = ["status", "is_active", "date_updated", "amount_refunded", "processed_at", "payment"]
        if notes:
            self.internal_notes = notes
            update_fields.append("internal_notes")

        self.save(update_fields=update_fields)

    def cancel(self):
        """Cancel the refund request."""
        if self.status != RefundStatus.PENDING:
            raise ValidationError(_('Only pending refunds can be cancelled.'))

        self._validate_status_transition(self.status, RefundStatus.CANCELLED)

        self.status = RefundStatus.CANCELLED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])


class RefundItem(CommonModel):
    """
    Individual items being refunded, supporting partial refunds.
    Normalized to track refund amounts per order item.
    """
    objects = RefundItemManager()

    refund = models.ForeignKey(
        "refunds.Refund",
        on_delete=models.PROTECT,
        related_name='items',
        verbose_name=_('Refund'),
        help_text=_('Refund containing this item')
    )
    order_item = models.ForeignKey(
        "orders.OrderItem",
        on_delete=models.PROTECT,
        related_name='refund_items',
        verbose_name=_('Order Item'),
        help_text=_('Order item being refunded')
    )
    quantity = models.PositiveIntegerField(
        _('Quantity Refunded'),
        validators=[MinValueValidator(1)],
        help_text=_('Quantity of items to refund')
    )
    unit_price = models.DecimalField(
        _('Unit Price'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text=_('Unit price at time of refund')
    )
    reason = models.CharField(
        _('Item Reason'),
        max_length=50,
        choices=RefundReason.choices,
        help_text=_('Reason for refunding this specific item')
    )

    class Meta:
        db_table = 'refund_items'
        verbose_name = _('Refund Item')
        verbose_name_plural = _('Refund Items')

        constraints = [
            # Prevent duplicate refund items
            models.UniqueConstraint(
                fields=['refund', 'order_item'],
                condition=models.Q(is_deleted=False),
                name='unique_order_item_per_active_refund'
            ),
        ]
        indexes = [
            models.Index(fields=['refund', 'is_deleted']),
            models.Index(fields=['order_item', 'is_deleted']),
            models.Index(fields=['quantity', 'unit_price']),
        ]

    def __str__(self):
        return f"{self.order_item.product.product_name} x {self.quantity} - Refund #{self.refund.refund_number}"

    @property
    def total_amount(self):
        """Calculate total refund amount for this item."""
        return self.unit_price * self.quantity

    def clean(self):
        """Validate refund item constraints considering soft deletion."""
        super().clean()

        if self.quantity > self.order_item.quantity:
            raise ValidationError(_('Refund quantity cannot exceed original order quantity.'))

        # Check active refunds (excluding soft-deleted ones)
        active_refunds = RefundItem.objects.filter(
            order_item=self.order_item,
            is_deleted=False,
            refund__status__in=[RefundStatus.PENDING, RefundStatus.APPROVED, RefundStatus.COMPLETED]
        ).exclude(refund=self.refund)  # Exclude current refund if updating

        total_refunded = active_refunds.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0

        if total_refunded + self.quantity > self.order_item.quantity:
            raise ValidationError(
                _('Total refunded quantity (%(total)s) cannot exceed original order quantity (%(max)s).') % {
                    'total': total_refunded + self.quantity,
                    'max': self.order_item.quantity
                }
            )

    def is_valid(self) -> bool:
        """
        Check if the refund item is valid according to business rules.

        Returns:
            bool: True if refund item is valid, False otherwise
        """
        if not super().is_valid():
            return False

        # Check required fields
        required_fields = [
            self.refund_id,
            self.order_item_id,
            self.quantity > 0,
            self.unit_price >= 0,
            self.reason in dict(RefundReason.choices)
        ]

        if not all(required_fields):
            return False

        # Check order item exists and is not deleted
        if hasattr(self, 'order_item') and (self.order_item.is_deleted or not self.order_item.is_active):
            return False

        # Check refund exists and is not deleted
        if hasattr(self, 'refund') and (self.refund.is_deleted or not self.refund.is_active):
            return False

        # Check quantity doesn't exceed available
        if hasattr(self, 'order_item') and self.quantity > self.order_item.quantity:
            return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if refund item can be safely soft-deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        if not super().can_be_deleted()[0]:
            return False, super().can_be_deleted()[1]

        # Check if refund is already completed
        if hasattr(self, 'refund') and self.refund.status == RefundStatus.COMPLETED:
            return False, "Cannot delete item from a completed refund"

        return True, ""

    def delete(self, *args, **kwargs):
        """Override delete to prevent deletion of items from completed refunds."""
        if hasattr(self, 'refund') and self.refund.status == RefundStatus.COMPLETED:
            raise ValidationError(_("Cannot delete item from a completed refund"))

        super().delete(*args, **kwargs)