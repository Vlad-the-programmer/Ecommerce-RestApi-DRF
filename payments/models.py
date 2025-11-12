from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel
from payments.enums import PaymentMethod, PaymentStatus
from payments.managers import PaymentManager


class Payment(CommonModel):
    """
    Represents a payment made toward an invoice.
    """
    objects = PaymentManager()

    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("Invoice"),
        help_text=_("Invoice associated with this payment."),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name=_("User"),
        help_text=_("User who made the payment (if applicable)."),
    )

    payment_reference = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("Payment Reference"),
        help_text=_("Unique transaction ID from the payment processor or internal system."),
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("Amount"),
        help_text=_("Amount paid in this transaction."),
    )

    currency = models.CharField(
        max_length=3,
        default="USD",
        verbose_name=_("Currency"),
        help_text=_("Currency code in ISO 4217 format (e.g., USD, EUR, PLN)."),
    )

    method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CREDIT_CARD,
        verbose_name=_("Payment Method"),
        help_text=_("Method used for payment."),
    )

    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        verbose_name=_("Payment Status"),
        help_text=_("Current status of the payment."),
    )

    transaction_date = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("Transaction Date"),
        help_text=_("Date and time when the payment occurred."),
    )

    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Confirmed At"),
        help_text=_("Timestamp when payment was confirmed (if applicable)."),
    )

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Notes"),
        help_text=_("Optional comments or metadata about the payment."),
    )

    class Meta:
        db_table = "payments"
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ["-transaction_date"]

        constraints = [
            # Unique reference constraint
            models.UniqueConstraint(
                fields=["payment_reference"],
                name="unique_payment_reference"
            ),

            # Payment must be non-negative
            models.CheckConstraint(
                check=Q(amount__gte=0),
                name="payment_non_negative_amount"
            ),

            # Payment cannot exist without invoice
            models.CheckConstraint(
                check=~Q(invoice__isnull=True),
                name="payment_invoice_required"
            ),

            # Completed payments must have confirmed_at timestamp
            models.CheckConstraint(
                check=~Q(status=PaymentStatus.COMPLETED) | Q(confirmed_at__isnull=False),
                name="payment_confirmed_at_required_for_completed"
            ),
        ]
        indexes = CommonModel.Meta.indexes + [
            # Core filters
            models.Index(fields=["invoice"], name="payment_invoice_idx"),
            models.Index(fields=["user"], name="payment_user_idx"),

            # Lookup by reference or method
            models.Index(fields=["payment_reference"], name="payment_reference_idx"),
            models.Index(fields=["method", "status"], name="payment_method_status_idx"),

            # Date-based and currency-based analytics
            models.Index(fields=["transaction_date", "currency"], name="payment_date_currency_idx"),
            models.Index(fields=["status", "is_deleted"], name="payment_status_idx"),
        ]

    def __str__(self):
        return f"Payment {self.payment_reference} ({self.amount} {self.currency}) - {self.status}"

    def is_valid(self) -> bool:
        """
        Check if the payment is valid according to business rules.

        Returns:
            bool: True if payment is valid, False otherwise
        """
        if not super().is_valid():
            return False

        # Check required fields
        if not all([self.invoice_id, self.amount, self.currency, self.method, self.status,
                    self.transaction_date, self.payment_reference]):
            return False

        # Check amount is positive
        if self.amount <= 0:
            return False

        # Check completed payments have confirmation timestamp
        if self.status == PaymentStatus.COMPLETED and not self.confirmed_at:
            return False

        # Check payment reference format if exists
        if self.payment_reference and not self.payment_reference.startswith('PAY-'):
            return False

        # Check invoice is not deleted
        if hasattr(self, 'invoice') and self.invoice.is_deleted:
            return False

        # Check currency is valid (basic check for 3 uppercase letters)
        if not (len(self.currency) == 3 and self.currency.isalpha() and self.currency.isupper()):
            return False

        return True

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        if is_new and not self.payment_reference:
            self.payment_reference = self.generate_payment_reference()

        if is_new and not self.transaction_date:
            self.transaction_date = timezone.now()

        if is_new and not self.status:
            self.status = PaymentStatus.PENDING

        super().save(*args, **kwargs)

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the payment can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        # Check parent class constraints first
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        # Check payment-specific constraints
        if self.is_successful:
            return False, "Cannot delete a completed payment"

        if self.status in [PaymentStatus.REFUNDED, PaymentStatus.PENDING]:
            status_display = dict(PaymentStatus.choices).get(self.status, self.status)
            return False, f"Cannot delete a payment with status '{status_display}'"

        return True, ""

    @property
    def is_successful(self):
        """Returns True if payment is successful."""
        return self.status == PaymentStatus.COMPLETED

    def _validate_status_transition(self, old_status: str, new_status: str) -> None:
        """Validate status transitions."""
        status_order = [
            PaymentStatus.PENDING,
            PaymentStatus.COMPLETED,
            PaymentStatus.REFUNDED,
            PaymentStatus.CANCELLED,
            PaymentStatus.FAILED,
        ]

        if old_status == new_status:
            return

        if old_status == PaymentStatus.CANCELLED:
            raise ValidationError(_("Cannot change status of a cancelled payment."))

        if old_status == PaymentStatus.COMPLETED and new_status != PaymentStatus.CANCELLED:
            raise ValidationError(_("Cannot modify a paid invoice."))

        if old_status == PaymentStatus.REFUNDED and new_status != PaymentStatus.CANCELLED:
            raise ValidationError(_("Cannot modify a refunded invoice."))

        if (status_order.index(new_status) < status_order.index(old_status) and
                new_status != PaymentStatus.CANCELLED and
                new_status != PaymentStatus.REFUNDED and
                new_status != PaymentStatus.COMPLETED and new_status != PaymentStatus.FAILED):
            raise ValidationError(_("Cannot move to a previous status."))

    def mark_completed(self, confirmed_at=None):
        """Mark the payment as completed."""
        self.status = PaymentStatus.COMPLETED
        self.is_active = False
        self.confirmed_at = confirmed_at or timezone.now()
        self.save(update_fields=["status", "confirmed_at", "is_active", "date_updated"])

    def mark_failed(self):
        """Mark the payment as failed."""
        self._validate_status_transition(self.status, PaymentStatus.FAILED)

        self.status = PaymentStatus.FAILED
        self.is_active = False
        self.save(update_fields=["status", "date_updated", "is_active"])

    def mark_refunded(self):
        """Mark the payment as refunded."""
        self._validate_status_transition(self.status, PaymentStatus.REFUNDED)

        self.status = PaymentStatus.REFUNDED
        self.is_active = False
        self.save(update_fields=["status", "date_updated", "is_active"])

    def mark_cancelled(self):
        """Mark the payment as cancelled."""
        self._validate_status_transition(self.status, PaymentStatus.CANCELLED)

        self.status = PaymentStatus.CANCELLED
        self.is_active = False
        self.save(update_fields=["status", "date_updated", "is_active"])

    def clean(self):
        """Business rule validations."""
        super().clean()

        if self.amount < 0:
            raise ValidationError({"amount": _("Payment amount cannot be negative.")})

        if self.status == PaymentStatus.COMPLETED and not self.confirmed_at:
            raise ValidationError({
                "confirmed_at": _("Completed payments must have a confirmation timestamp.")
            })

            # Ensure invoice exists and is not deleted
        if not hasattr(self, 'invoice') or (self.invoice_id and self.invoice.is_deleted):
            raise ValidationError({"invoice": _("Cannot create payment for non-existent or deleted invoice.")})

    def generate_payment_reference(self):
        """Generate unique payment reference."""
        import random
        import string
        return f"PAY-{timezone.now().strftime('%Y%m%d')}- \
                {''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"

    def process_payment(self, payment_data: dict) -> bool:
        """
        Process the payment using the provided payment data.

        Args:
            payment_data: Dictionary containing payment details

        Returns:
            bool: True if payment was successful, False otherwise
        """
        try:
            # TODO: Add payment processing logic
            self.mark_completed()
            return True
        except Exception as e:
            self.status = PaymentStatus.FAILED
            self.notes = f"Payment failed: {str(e)}"
            self.save()
            return False

    def refund(self, amount: Decimal = None, reason: str = "", refund_method: str = "") -> 'Payment':
        """
        Create a refund for this payment.

        Args:
            amount: Amount to refund (defaults to full amount)
            reason: Reason for the refund

        Returns:
            Payment: New refund payment record
        """
        if self.status != PaymentStatus.COMPLETED:
            raise ValidationError("Only completed payments can be refunded")

        refund_amount = amount or self.amount
        if refund_amount > self.amount:
            raise ValidationError("Refund amount cannot exceed original payment amount")

        refund = Payment.objects.create(
            invoice=self.invoice,
            user=self.user,
            amount=-refund_amount,
            currency=self.currency,
            method=refund_method or self.method,
            status=PaymentStatus.REFUNDED,
            notes=f"Refund of payment {self.payment_reference}. {reason}".strip()
        )
        refund.mark_completed()

        # TODO: Add payment_data for payment processing
        self.process_payment(payment_data={})

        return refund

    @property
    def status_display(self) -> str:
        """Return the human-readable status."""
        return dict(PaymentStatus.choices).get(self.status, self.status)

    def get_amount_display(self) -> str:
        """Return formatted amount with currency."""
        from django.utils.numberformat import format
        return f"{format(self.amount, '.', 2)} {self.currency}"