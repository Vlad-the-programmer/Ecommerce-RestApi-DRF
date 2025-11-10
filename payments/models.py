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

    def delete(self, *args, **kwargs):
        if self.is_successful:
            raise ValidationError("Cannot delete payment with completed status")

        super().delete(*args, **kwargs)

    @property
    def is_successful(self):
        """Returns True if payment is successful."""
        return self.status == PaymentStatus.COMPLETED

    def mark_completed(self, confirmed_at=None):
        """Mark the payment as completed."""
        self.status = PaymentStatus.COMPLETED
        self.confirmed_at = confirmed_at or timezone.now()
        self.save(update_fields=["status", "confirmed_at", "date_updated"])

    def mark_failed(self):
        """Mark the payment as failed."""
        self.status = PaymentStatus.FAILED
        self.save(update_fields=["status", "date_updated"])

    def mark_refunded(self):
        """Mark the payment as refunded."""
        self.status = PaymentStatus.REFUNDED
        self.save(update_fields=["status", "date_updated"])

    def mark_cancelled(self):
        """Mark the payment as cancelled."""
        self.status = PaymentStatus.CANCELLED
        self.save(update_fields=["status", "date_updated"])

    def clean(self):
        """Business rule validations."""
        super().clean()

        if self.amount < 0:
            raise ValidationError({"amount": _("Payment amount cannot be negative.")})

        if self.status == PaymentStatus.COMPLETED and not self.confirmed_at:
            raise ValidationError({
                "confirmed_at": _("Completed payments must have a confirmation timestamp.")
            })

        # Ensure invoice is not deleted
        if self.invoice_id and self.invoice.is_deleted:
            raise ValidationError(_("Cannot create payment for deleted invoice."))
