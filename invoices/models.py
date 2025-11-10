from django.core.exceptions import ValidationError

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, F
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel
from invoices.enums import InvoiceStatus
from invoices.managers import InvoiceManager


class Invoice(CommonModel):
    """
    Represents a customer invoice for product or service purchases.
    Inherits audit fields, soft deletion, and indexing from CommonModel.
    """

    objects = InvoiceManager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("User"),
        help_text=_("User or customer associated with this invoice."),
    )

    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Invoice Number"),
        help_text=_("Unique invoice number for external reference."),
    )

    issue_date = models.DateField(
        verbose_name=_("Issue Date"),
        help_text=_("Date when the invoice was created."),
    )

    due_date = models.DateField(
        verbose_name=_("Due Date"),
        help_text=_("Date when the invoice is due for payment."),
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("Total Amount"),
        help_text=_("Total amount billed in this invoice."),
    )

    currency = models.CharField(
        max_length=3,
        default="USD",
        verbose_name=_("Currency"),
        help_text=_("Currency code in ISO 4217 format (e.g., USD, EUR, PLN)."),
    )

    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        verbose_name=_("Invoice Status"),
        help_text=_("Current status of this invoice."),
    )

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Notes"),
        help_text=_("Additional information or comments about the invoice."),
    )

    class Meta:
        db_table = "invoices"
        verbose_name = _("Invoice")
        verbose_name_plural = _("Invoices")
        ordering = ["-date_created"]

        constraints = [
            # Unique invoice number constraint
            models.UniqueConstraint(
                fields=["invoice_number"],
                name="unique_invoice_number"
            ),

            # Logical date check: due_date >= issue_date
            models.CheckConstraint(
                check=Q(due_date__gte=F("issue_date")),
                name="invoice_due_date_after_issue_date"
            ),

            # Non-negative total amount
            models.CheckConstraint(
                check=Q(total_amount__gte=0),
                name="invoice_non_negative_total"
            ),

            # Active invoices must not be deleted
            models.CheckConstraint(
                check=Q(is_deleted=False) | Q(status__in=[InvoiceStatus.CANCELLED]),
                name="invoice_deleted_only_if_cancelled"
            ),
        ]
        indexes = CommonModel.Meta.indexes + [
            # Core lookups
            models.Index(fields=["user"], name="invoice_user_idx"),
            models.Index(fields=["invoice_number"], name="invoice_number_idx"),

            # Status-based and currency-based filtering
            models.Index(fields=["status", "is_deleted"], name="invoice_status_idx"),
            models.Index(fields=["currency", "is_deleted"], name="invoice_currency_idx"),

            # Date-based reporting and overdue detection
            models.Index(fields=["issue_date", "due_date"], name="invoice_dates_idx"),
            models.Index(fields=["due_date", "status"], name="invoice_due_status_idx"),

            # Aggregation-friendly composite index
            models.Index(fields=["user", "status", "is_deleted"], name="invoice_user_status_idx"),
        ]

    def __str__(self):
        return f"Invoice #{self.invoice_number} - {self.user} ({self.status})"

    def delete(self, *args, **kwargs):
        if self.is_paid:
            raise ValidationError("Cannot delete invoice with completed payments")

        super().delete(*args, **kwargs)

    @property
    def is_overdue(self):
        """Determine if the invoice is overdue (unpaid and past due date)."""
        from django.utils import timezone
        return (
            self.status not in [InvoiceStatus.PAID, InvoiceStatus.CANCELLED]
            and self.due_date < timezone.now().date()
        )

    @property
    def is_paid(self):
        """Determine if the invoice is paid."""
        return self.status == InvoiceStatus.PAID

    def mark_issued(self):
        """Mark the invoice as issued."""
        self.status = InvoiceStatus.ISSUED
        self.save(update_fields=["status"])

    def mark_paid(self):
        """Mark the invoice as paid."""
        self.status = InvoiceStatus.PAID
        self.save(update_fields=["status"])

    def mark_cancelled(self):
        """Mark the invoice as cancelled."""
        self.status = InvoiceStatus.CANCELLED
        self.save(update_fields=["status"])

    def mark_overdue(self):
        """Mark the invoice as overdue."""
        self.status = InvoiceStatus.OVERDUE
        self.save(update_fields=["status"])

    def clean(self):
        """Custom validation for business logic."""
        super().clean()

        if self.user.is_deleted:
            raise ValidationError(_("Cannot create invoice for deleted user"))

        # Prevent negative amounts
        if self.total_amount < 0:
            raise ValidationError({"total_amount": _("Total amount cannot be negative.")})

        # Ensure due date is after issue date
        if self.due_date < self.issue_date:
            raise ValidationError({"due_date": _("Due date cannot be before issue date.")})

