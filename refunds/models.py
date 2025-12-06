from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal, DecimalException

from rest_framework.exceptions import ValidationError

from common.models import CommonModel
from refunds.enums import RefundStatus, RefundReason, RefundMethod, ACTIVE_REFUND_STATUSES
from refunds.managers import RefundManager, RefundItemManager

import logging

from refunds.notifier import RefundNotifier

logger = logging.getLogger(__name__)


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
    currency = models.CharField(
        _('Currency'),
        max_length=3,
        default='USD',
        help_text=_('Currency of the refund amount')
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
    date_completed = models.DateTimeField(
        _('Date Completed'),
        null=True,
        blank=True,
        help_text=_('When the refund was completed')
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
    rejection_reason = models.TextField(
        _('Rejection Reason'),
        blank=True,
        null=True,
        help_text=_('Reason for rejecting the refund')
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
            models.CheckConstraint(
                check=models.Q(amount_approved__lte=models.F('amount_requested')),
                name='approved_amount_lte_requested'
            ),
            models.CheckConstraint(
                check=models.Q(amount_refunded__lte=models.F('amount_approved')),
                name='refunded_amount_lte_approved'
            ),
            models.UniqueConstraint(
                fields=['order', 'status'],
                condition=models.Q(status__in=['pending', 'processing']),
                name='unique_pending_refund_per_order'
            ),
        ]
        indexes = CommonModel.Meta.indexes + [ 
            models.Index(fields=['refund_number']),
            models.Index(fields=['status', 'is_deleted']),
            models.Index(fields=['order', 'status']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['payment', 'status']),
            models.Index(fields=['refund_number', 'is_deleted']),
            models.Index(fields=['status', 'is_deleted', 'requested_at']),
            models.Index(fields=['customer', 'is_deleted', 'requested_at']),

            models.Index(fields=['requested_at', 'status']),
            models.Index(fields=['processed_at', 'status']),
            models.Index(fields=['date_completed', 'status']),
            models.Index(fields=['requested_at', 'customer']),
            models.Index(fields=['processed_at', 'customer']),
            models.Index(fields=['date_completed', 'customer']),
            models.Index(fields=['is_deleted', 'status', 'requested_at']),
            models.Index(fields=['refund_method', 'is_deleted', 'status']),
            models.Index(fields=['status', 'amount_requested']),
            models.Index(fields=['refund_method', 'status']),
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
        validation_errors = []

        if not super().is_valid():
            validation_errors.append("Base validation failed (inactive or deleted)")

        if not self.refund_number:
            validation_errors.append("Refund number is required")
        if not self.order_id:
            validation_errors.append("Order is required")
        if not self.payment_id:
            validation_errors.append("Payment is required")
        if not self.customer_id:
            validation_errors.append("Customer is required")
        if self.status not in dict(RefundStatus.choices):
            validation_errors.append(f"Invalid status: {self.status}")
        if self.reason not in dict(RefundReason.choices):
            validation_errors.append(f"Invalid reason: {self.reason}")
        if self.refund_method not in dict(RefundMethod.choices):
            validation_errors.append(f"Invalid refund method: {self.refund_method}")
        if self.amount_requested is None:
            validation_errors.append("Amount requested is required")
        if self.requested_at is None:
            validation_errors.append("Requested at date is required")

        try:
            if self.amount_requested <= 0:
                validation_errors.append("Amount requested must be greater than 0")

            if self.amount_approved is not None and self.amount_approved < 0:
                validation_errors.append("Amount approved cannot be negative")

            if self.amount_refunded < 0:
                validation_errors.append("Amount refunded cannot be negative")

            if self.amount_approved is not None and self.amount_approved > self.amount_requested:
                validation_errors.append("Amount approved cannot be greater than amount requested")

            if self.amount_refunded > 0 and (self.amount_approved is None or self.amount_refunded > self.amount_approved):
                validation_errors.append("Amount refunded cannot be greater than amount approved")

        except (TypeError, DecimalException) as e:
            validation_errors.append(f"Error in amount validation: {str(e)}")

        if self.status == RefundStatus.COMPLETED:
            if not self.processed_at:
                validation_errors.append("Processed date is required for completed refunds")
            if self.amount_refunded <= 0:
                validation_errors.append("Amount refunded must be greater than 0 for completed refunds")
            if self.amount_approved is None or self.amount_approved <= 0:
                validation_errors.append("Valid approved amount is required for completed refunds")

        if self.processed_at and self.processed_at < self.requested_at:
            validation_errors.append("Processed date cannot be before requested date")

        if hasattr(self, 'order') and (not self.order or self.order.is_deleted):
            validation_errors.append("Order is deleted or does not exist")

        if hasattr(self, 'payment'):
            if not self.payment:
                validation_errors.append("Payment does not exist")
            elif self.payment.is_deleted or not hasattr(self.payment, 'is_successful') or not self.payment.is_successful:
                validation_errors.append("Payment is invalid or not successful")

        if hasattr(self, 'customer') and (not self.customer or not self.customer.is_active):
            validation_errors.append("Customer is inactive or does not exist")

        if hasattr(self, 'items'):
            try:
                total_items_amount = sum(item.total_amount for item in self.items.all() if not item.is_deleted)
                if abs(total_items_amount - self.amount_requested) > Decimal('0.01'):  # Allow for small rounding differences
                    validation_errors.append(
                        f"Total items amount ({total_items_amount}) does not match requested amount ({self.amount_requested})")
            except (TypeError, ValueError, DecimalException) as e:
                validation_errors.append(f"Error calculating total items amount: {str(e)}")

        if validation_errors:
            logger.warning(
                f"Refund validation failed for {self} - "
                f"Refund: {getattr(self, 'refund_number', 'None')}, "
                f"Order: {getattr(self, 'order_id', 'None')}, "
                f"Customer: {getattr(self, 'customer_id', 'None')}. "
                f"Errors: {', '.join(validation_errors)}"
            )

        return not bool(validation_errors)

    def save(self, *args, **kwargs):
        """Override save to generate refund number and handle status transitions."""
        is_new = self._state.adding

        if is_new and not self.refund_number:
            self.refund_number = self.generate_refund_number()

        super().save(*args, **kwargs)

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the refund can be safely soft-deleted.

        Returns:
            Tuple[bool, str]: (can_delete, reason)
                - can_delete: True if the refund can be deleted, False otherwise
                - reason: Explanation if deletion is not allowed
        """
        base_can_delete, reason = super().can_be_deleted()
        if not base_can_delete:
            return False, reason

        if self.status == RefundStatus.COMPLETED:
            return False, "Completed refunds cannot be deleted"

        if self.amount_refunded > 0:
            return False, "Cannot delete refund with processed refunds"

        if self.status in [RefundStatus.CANCELLED, RefundStatus.REJECTED]:
            return True, ""

        if self.status in [RefundStatus.PENDING, RefundStatus.APPROVED]:
            return False, "Cannot delete refund in pending or approved state"

        return True, ""

    def generate_refund_number(self):
        """Generate unique refund number."""
        import random
        import string
        return f"REF-{timezone.now().strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"

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

    def update_amounts(self):
        """
        Update the refund amounts based on the current refund items.
        This should be called after adding, updating, or removing refund items.
        """
        if self.status == RefundStatus.COMPLETED:
            logger.warning(f"Cannot update amounts for completed refund {self.refund_number}")
            return False

        try:
            # Calculate total from all non-deleted items
            total_amount = Decimal('0.00')
            for item in self.items.filter(is_deleted=False):
                total_amount += item.total_amount

            # Update the requested amount
            self.amount_requested = total_amount
            
            # If no items left, cancel the refund
            if total_amount == 0 and self.items.filter(is_deleted=False).count() == 0:
                self.status = RefundStatus.CANCELLED
                logger.info(f"No items left in refund {self.refund_number}, status set to CANCELLED")
            
            # Save the changes
            self.save(update_fields=['amount_requested', 'status', 'date_updated'])
            logger.info(f"Updated amounts for refund {self.refund_number}: amount_requested={total_amount}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating amounts for refund {self.refund_number}: {str(e)}")
            return False

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
        """
        Approve the refund request with transaction and logging.
        
        Args:
            approved_amount (Decimal, optional): The approved refund amount. Defaults to requested amount.
            processed_by (User, optional): User who processed the approval.
            
        Raises:
            ValidationError: If refund cannot be approved
        """
        logger.info(
            f"Starting refund approval - Refund: {self.refund_number}, "
            f"Status: {self.status}, Requested Amount: {self.amount_requested}, "
            f"Approved Amount: {approved_amount}"
        )
        
        if self.status != RefundStatus.PENDING:
            error_msg = f'Only pending refunds can be approved. Current status: {self.status}'
            logger.error(f"Refund approval failed: {error_msg} - Refund: {self.refund_number}")
            raise ValidationError(_(error_msg))
            
        try:
            self._validate_status_transition(self.status, RefundStatus.APPROVED)
            
            old_status = self.status
            self.status = RefundStatus.APPROVED
            self.is_active = False
            self.amount_approved = approved_amount or self.amount_requested
            self.processed_by = processed_by
            self.processed_at = timezone.now()

            update_fields = [
                "status", "is_active", "date_updated",
                "amount_approved", "processed_by", "processed_at"
            ]
            self.save(update_fields=update_fields)

            logger.info(
                f"Successfully approved refund - Refund: {self.refund_number}, "
                f"Status: {old_status} -> {self.status}, "
                f"Amount Approved: {self.amount_approved}"
            )
                
        except ValidationError as ve:
            logger.error(
                f"Validation error approving refund {self.refund_number}: {str(ve)}",
                exc_info=True
            )
            raise
        except Exception as e:
            logger.critical(
                f"Unexpected error approving refund {self.refund_number}: {str(e)}",
                exc_info=True
            )
            raise ValidationError(_("An error occurred while approving the refund."))

    def complete(self, refunded_amount=None, processed_by=None):
        """
        Mark refund as completed with transaction and logging.
        
        Args:
            refunded_amount (Decimal, optional): The actual amount refunded. Defaults to approved amount.
            processed_by (User, optional): User who processed the completion.
            
        Raises:
            ValidationError: If refund cannot be completed
        """
        logger.info(
            f"Starting refund completion - Refund: {self.refund_number}, "
            f"Status: {self.status}, Approved Amount: {self.amount_approved}, "
            f"Refunded Amount: {refunded_amount}"
        )
        
        if self.status != RefundStatus.APPROVED:
            error_msg = f'Only approved refunds can be completed. Current status: {self.status}'
            logger.error(f"Refund completion failed: {error_msg} - Refund: {self.refund_number}")
            raise ValidationError(_(error_msg))
            
        try:
            self._validate_status_transition(self.status, RefundStatus.COMPLETED)
            
            old_status = self.status
            self.status = RefundStatus.COMPLETED
            self.is_active = False
            self.amount_refunded = refunded_amount or self.amount_approved
            self.processed_at = timezone.now()
            self.processed_by = processed_by
            self.date_completed = timezone.now()

            try:
                logger.info(f"Initiating payment refund - Refund: {self.refund_number}, Amount: {self.amount_refunded}")
                self.payment.refund(self.amount_refunded, self.reason, self.refund_method)
                logger.info(f"Payment refund successful - Refund: {self.refund_number}")
            except Exception as e:
                logger.error(
                    f"Payment refund failed - Refund: {self.refund_number}, "
                    f"Error: {str(e)}",
                    exc_info=True
                )
                raise ValidationError(_("Failed to process payment refund."))

            update_fields = [
                "status", "is_active", "date_updated", "amount_refunded",
                "processed_at", "payment", "processed_by"
            ]
            self.save(update_fields=update_fields)

            logger.info(
                f"Successfully completed refund - Refund: {self.refund_number}, "
                f"Status: {old_status} -> {self.status}, "
                f"Amount Refunded: {self.amount_refunded}"
            )
                
        except ValidationError as ve:
            logger.error(
                f"Validation error completing refund {self.refund_number}: {str(ve)}",
                exc_info=True
            )
            raise
        except Exception as e:
            logger.critical(
                f"Unexpected error completing refund {self.refund_number}: {str(e)}",
                exc_info=True
            )
            raise ValidationError(_("An error occurred while completing the refund."))

    def reject(self, processed_by=None, notes=None, rejection_reason=None):
        """
        Reject the refund request with transaction and logging.
        
        Args:
            processed_by (User, optional): User who processed the rejection.
            notes (str, optional): Internal notes about the rejection.
            
        Raises:
            ValidationError: If refund cannot be rejected
        """
        logger.info(
            f"Starting refund rejection - Refund: {self.refund_number}, "
            f"Status: {self.status}, Notes: {bool(notes)}"
        )
        
        if self.status != RefundStatus.PENDING:
            error_msg = f'Only pending refunds can be rejected. Current status: {self.status}'
            logger.error(f"Refund rejection failed: {error_msg} - Refund: {self.refund_number}")
            raise ValidationError(_(error_msg))
            
        try:
            self._validate_status_transition(self.status, RefundStatus.REJECTED)
            
            old_status = self.status
            self.status = RefundStatus.REJECTED
            self.is_active = False
            self.processed_by = processed_by
            self.processed_at = timezone.now()

            update_fields = [
                "status", "is_active", "date_updated",
                "processed_at", "processed_by"
            ]

            if notes:
                self.internal_notes = notes
                update_fields.append("internal_notes")

            if rejection_reason:
                self.rejection_reason = rejection_reason
                update_fields.append("rejection_reason")

            self.save(update_fields=update_fields)

            logger.info(
                f"Successfully rejected refund - Refund: {self.refund_number}, "
                f"Status: {old_status} -> {self.status}"
                f"Rejection Reason: {self.rejection_reason}"
            )

        except ValidationError as ve:
            logger.error(
                f"Validation error rejecting refund {self.refund_number}: {str(ve)}",
                exc_info=True
            )
            raise
        except Exception as e:
            logger.critical(
                f"Unexpected error rejecting refund {self.refund_number}: {str(e)}",
                exc_info=True
            )
            raise ValidationError(_("An error occurred while rejecting the refund."))

    def cancel(self, cancelled_by=None):
        """Cancel the refund request."""
        if self.status != RefundStatus.PENDING:
            raise ValidationError(_('Only pending refunds can be cancelled.'))


        try:
            self._validate_status_transition(self.status, RefundStatus.CANCELLED)

            self.status = RefundStatus.CANCELLED
            self.is_active = False
            self.processed_by = cancelled_by
            self.processed_at = timezone.now()
            self.save(update_fields=["status", "is_active", "date_updated"])
            logger.info(f"Auto-cancelled refund {self.refund_number} before deletion")
        except Exception as e:
            logger.error(f"Failed to auto-cancel refund {self.refund_number}: {str(e)}")

    def send_notification(self, notification_type=None, notifier=None):
        """Send a notification for the refund."""
        if notifier is None:
            notifier = RefundNotifier(self)

        if notification_type == RefundStatus.APPROVED:
            notifier.send_approval_notification()
        elif notification_type == RefundStatus.REJECTED:
            notifier.send_rejection_notification()
        elif notification_type == RefundStatus.CANCELLED:
            notifier.send_cancellation_notification()
        elif notification_type == RefundStatus.COMPLETED:
            notifier.send_completion_notification()
        else:
            logger.error(f"Invalid notification type: {notification_type}"
                         f"Types are: {RefundStatus.APPROVED, RefundStatus.REJECTED, 
                         RefundStatus.CANCELLED, RefundStatus.COMPLETED}"
                         )

            raise ValueError(f"Invalid notification type: {notification_type}")
        pass

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
        indexes = CommonModel.Meta.indexes + [ 
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
            refund__status__in=[*ACTIVE_REFUND_STATUSES, RefundStatus.COMPLETED]
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
        validation_errors = []

        # Call parent's is_valid first
        if not super().is_valid():
            validation_errors.append("Base validation failed (inactive or deleted)")

        # Check required fields
        if not self.refund_id:
            validation_errors.append("Refund reference is required")
        if not self.order_item_id:
            validation_errors.append("Order item reference is required")
        if not (isinstance(self.quantity, int) and self.quantity > 0):
            validation_errors.append(f"Quantity must be a positive integer, got {self.quantity}")
        if not (isinstance(self.unit_price, (Decimal, float, int)) and self.unit_price >= 0):
            validation_errors.append(f"Unit price must be a non-negative number, got {self.unit_price}")
        if self.reason not in dict(RefundReason.choices):
            validation_errors.append(f"Invalid reason: {self.reason}")

        # Check order item exists and is not deleted
        if hasattr(self, 'order_item'):
            if not self.order_item:
                validation_errors.append("Order item does not exist")
            elif self.order_item.is_deleted or not self.order_item.is_active:
                validation_errors.append("Order item is not available for refund")
            else:
                # Check quantity doesn't exceed available
                try:
                    if self.quantity > self.order_item.quantity:
                        validation_errors.append(
                            f"Refund quantity ({self.quantity}) exceeds available quantity ({self.order_item.quantity_available_for_refund})")
                except (AttributeError, ValueError) as e:
                    validation_errors.append(f"Error checking available quantity: {str(e)}")

        # Check refund exists and is not deleted
        if hasattr(self, 'refund'):
            if not self.refund:
                validation_errors.append("Refund does not exist")
            elif self.refund.is_deleted or not self.refund.is_active:
                validation_errors.append("Refund is not active")
            elif self.refund.status == RefundStatus.COMPLETED:
                validation_errors.append("Cannot modify items of a completed refund")

        if validation_errors:
            logger.warning(
                f"RefundItem validation failed - "
                f"ID: {getattr(self, 'id', 'new')}, "
                f"Refund: {getattr(self, 'refund_id', 'None')}, "
                f"OrderItem: {getattr(self, 'order_item_id', 'None')}. "
                f"Errors: {', '.join(validation_errors)}"
            )

        return not bool(validation_errors)

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the refund item can be safely soft-deleted.

        Returns:
            Tuple[bool, str]: (can_delete, reason)
                - can_delete: True if the item can be deleted, False otherwise
                - reason: Explanation if deletion is not allowed
        """
        # Check base class can_be_deleted first
        base_can_delete, reason = super().can_be_deleted()
        if not base_can_delete:
            logger.debug(f"RefundItem {getattr(self, 'id', 'new')} base validation failed: {reason}")
            return False, reason

        # Check if refund is already deleted
        if self.is_deleted:
            return False, "Refund item is already deleted"

        # Check if refund exists and is not completed
        if hasattr(self, 'refund'):
            if not self.refund:
                return False, "Associated refund does not exist"
            
            if self.refund.status == RefundStatus.COMPLETED:
                return False, "Cannot delete item from a completed refund"
            
            if self.refund.status == RefundStatus.REJECTED:
                return True, ""  # Allow deletion of items from rejected refunds
            
            # For pending/approved refunds, check if the refund is still in a modifiable state
            if self.refund.status in ACTIVE_REFUND_STATUSES:
                # Check if the refund item has already been processed
                if hasattr(self, 'processed_at') and self.processed_at:
                    return False, "Cannot delete already processed refund item"

        return True, ""

    def delete(self, *args, **kwargs):
        """
        Soft delete the refund item after validation and update parent refund amounts.
        
        Raises:
            ValidationError: If the item cannot be deleted
        """
        refund = getattr(self, 'refund', None)
        
        try:
            super().delete(*args, **kwargs)
            
            # Update parent refund amounts if needed
            if refund and not refund.is_deleted:
                refund.update_amounts()
                logger.info(f"Updated amounts after deleting refund item {self.id} from refund {refund.refund_number}")
                
        except Exception as e:
            logger.error(f"Error deleting refund item {getattr(self, 'id', 'unknown')}: {str(e)}")
            raise
        else:
            logger.info(f"Soft deleted refund item {getattr(self, 'id', 'unknown')} "
                        f"from refund {getattr(refund, 'refund_number', 'unknown')}")
