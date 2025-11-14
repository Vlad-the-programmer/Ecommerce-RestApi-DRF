from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel
from invoices.enums import InvoiceStatus
from invoices.managers import InvoiceManager
from payments.models import Payment


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

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("Order"),
        help_text=_("The order this invoice is associated with."),
        null=True,
        blank=True
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

            models.UniqueConstraint(
                fields=["order"],
                name="unique_active_order_invoice",
                condition=Q(is_deleted=False,
                            status__in=[InvoiceStatus.DRAFT, InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE])
            ),
            models.CheckConstraint(
                check=Q(order__isnull=True) | ~Q(status=InvoiceStatus.DRAFT),
                name="draft_invoice_must_have_no_order"
            ),
            models.CheckConstraint(
                check=~Q(status=InvoiceStatus.PAID) | Q(order__isnull=False),
                name="paid_invoice_must_have_order"
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
            models.Index(fields=["order", "is_deleted"], name="invoice_order_idx"),
            models.Index(fields=["order", "status", "is_deleted"], name="invoice_order_status_idx"),
            models.Index(fields=["status", "due_date", "is_deleted"], name="invoice_status_due_date_idx"),
            models.Index(fields=["issue_date", "due_date", "status"], name="invoice_dates_status_idx"),
            models.Index(fields=["total_amount", "currency", "is_deleted"], name="invoice_amount_currency_idx"),
        ]

    def __str__(self):
        return f"Invoice #{self.invoice_number} - {self.user} ({self.status})"

    def is_valid(self) -> bool:
        """
        Check if the invoice is valid according to business rules.

        Returns:
            bool: True if invoice is valid, False otherwise with detailed logging
        """
        import logging
        logger = logging.getLogger(__name__)

        # Basic model validation
        if not super().is_valid():
            logger.warning(f"Invoice {self.id} failed basic model validation")
            return False

        # Check required fields
        required_fields = {
            'user_id': self.user_id,
            'invoice_number': self.invoice_number,
            'issue_date': self.issue_date,
            'due_date': self.due_date,
            'total_amount': self.total_amount is not None,
            'currency': self.currency,
            'status': self.status
        }

        missing_fields = [field for field, has_value in required_fields.items() if not has_value]
        if missing_fields:
            logger.warning(f"Invoice {self.id} is missing required fields: {', '.join(missing_fields)}")
            return False

        # Check amount is non-negative
        if not isinstance(self.total_amount, (int, float, Decimal)) or self.total_amount < 0:
            logger.warning(f"Invoice {self.id} has invalid amount: {self.total_amount}")
            return False

        # Check date validity
        if not isinstance(self.issue_date, (timezone.datetime, timezone.date)):
            logger.warning(f"Invoice {self.id} has invalid issue date: {self.issue_date}")
            return False

        if not isinstance(self.due_date, (timezone.datetime, timezone.date)):
            logger.warning(f"Invoice {self.id} has invalid due date: {self.due_date}")
            return False

        # Check due date is not before issue date
        if self.due_date < self.issue_date:
            logger.warning(
                f"Invoice {self.id} has due date ({self.due_date}) before issue date ({self.issue_date})"
            )
            return False

        # Check invoice number format
        if not (self.invoice_number and isinstance(self.invoice_number, str)):
            logger.warning(f"Invoice {self.id} has invalid invoice number format")
            return False

        # Check currency format (3 uppercase letters)
        if not (isinstance(self.currency, str) and
                len(self.currency) == 3 and
                self.currency.isalpha() and
                self.currency.isupper()):
            logger.warning(f"Invoice {self.id} has invalid currency code: {self.currency}")
            return False

        # Status-specific validations
        if self.status == InvoiceStatus.PAID and not self.is_fully_paid:
            logger.warning(
                f"Invoice {self.id} is marked as PAID but amount paid is less than total amount"
            )
            return False

        if self.status == InvoiceStatus.CANCELLED and self.is_fully_paid:
            logger.warning(
                f"Invoice {self.id} is marked as CANCELLED but has been fully paid"
            )
            return False

        # Check order relationship rules
        if self.status != InvoiceStatus.DRAFT and not self.order_id:
            logger.warning(
                f"Invoice {self.id} is not a draft but has no associated order"
            )
            return False

        if self.order_id and hasattr(self, 'order') and self.order.is_deleted:
            logger.warning(
                f"Invoice {self.id} is associated with a deleted order"
            )
            return False

        logger.debug(f"Invoice {self.id} validation successful")
        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if invoice can be safely soft-deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        import logging
        logger = logging.getLogger(__name__)

        # Check parent class constraints
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            logger.warning(f"Invoice {self.id} cannot be deleted: {reason}")
            return can_delete, reason

        # Check if invoice is paid
        if self.status == InvoiceStatus.PAID:
            message = "Cannot delete a paid invoice"
            logger.warning(f"{message} (Invoice ID: {self.id})")
            return False, message

        # Check for associated payments
        if hasattr(self, 'payments') and self.payments.exists():
            payment_count = self.payments.count()
            message = f"Cannot delete invoice with {payment_count} associated payment(s)"
            logger.warning(f"{message} (Invoice ID: {self.id})")
            return False, message

        # Check for associated order if applicable
        if hasattr(self, 'order') and self.order:
            order_can_be_deleted, reason = self.order.can_be_deleted()
            if not order_can_be_deleted:
                logger.warning(
                    f"Cannot delete invoice {self.id} due to order constraints: {reason}"
                )
                return False, reason

        logger.info(f"Invoice {self.id} can be safely deleted")
        return True, ""

    @property
    def is_overdue(self):
        """Determine if the invoice is overdue (unpaid and past due date)."""
        from django.utils import timezone
        return (
            self.status not in [InvoiceStatus.PAID, InvoiceStatus.CANCELLED]
            and self.due_date < timezone.now().date()
        )

    @property
    def days_until_due(self) -> int:
        """Return number of days until the invoice is due. Negative if overdue."""
        return (self.due_date - timezone.now().date()).days

    @property
    def is_fully_paid(self) -> bool:
        """Check if the invoice is fully paid, considering partial payments."""
        if self.status == InvoiceStatus.PAID:
            return True
        # If you implement a payment tracking system later:
        # return self.amount_paid >= self.total_amount
        return False

    @property
    def amount_due(self) -> Decimal:
        """Calculate the amount still due on this invoice."""
        if self.status == InvoiceStatus.PAID:
            return Decimal('0.00')
        # If you implement a payment tracking system:
        # return max(self.total_amount - self.amount_paid, Decimal('0.00'))
        return self.total_amount

    def generate_invoice_number(self) -> str:
        """Generate a sequential invoice number."""
        prefix = "INV"
        date_part = timezone.now().strftime("%Y%m")

        last_invoice = Invoice.objects.filter(
            invoice_number__startswith=f"{prefix}-{date_part}-"
        ).order_by('-date_created').first()

        if last_invoice and last_invoice.invoice_number:
            try:
                last_num = int(last_invoice.invoice_number.split('-')[-1])
                new_num = last_num + 1
            except (IndexError, ValueError):
                new_num = 1
        else:
            new_num = 1

        return f"{prefix}-{date_part}-{new_num:05d}"

    @property
    def status_display(self):
        """Get the display name of the invoice status."""
        return self.status.name

    def mark_issued(self):
        """Mark the invoice as issued."""
        self._validate_status_transition(self.status, InvoiceStatus.ISSUED)

        self.status = InvoiceStatus.ISSUED
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_paid(self):
        """Mark the invoice as paid."""
        self._validate_status_transition(self.status, InvoiceStatus.PAID)

        self.status = InvoiceStatus.PAID

        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_cancelled(self):
        """Mark the invoice as cancelled."""
        self.status = InvoiceStatus.CANCELLED
        self.is_active = False
        self.save(update_fields=["status", "is_active", "date_updated"])

    def mark_overdue(self):
        """Mark the invoice as overdue."""
        self._validate_status_transition(self.status, InvoiceStatus.OVERDUE)

        self.status = InvoiceStatus.OVERDUE
        self.save(update_fields=["status"])

    def mark_draft(self):
        """Mark the invoice as draft."""
        self._validate_status_transition(self.status, InvoiceStatus.DRAFT)

        self.status = InvoiceStatus.DRAFT
        self.save(update_fields=["status"])

    def save(self, *args, **kwargs):
        """Override save to handle invoice number generation and validation."""
        is_new = self._state.adding

        if is_new and not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()

        if is_new and not self.issue_date:
            self.issue_date = timezone.now().date()

        if is_new and not self.due_date:
            self.due_date = self.issue_date + timedelta(days=30)  # 30-day default payment term

        if is_new:
            self.mark_issued()

        super().save(*args, **kwargs)

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

        # Validate invoice status transitions
        if not self._state.adding:
            old_instance = Invoice.objects.get(pk=self.pk)
            self._validate_status_transition(old_instance.status, self.status)

    def _validate_status_transition(self, old_status: str, new_status: str) -> None:
        """Validate status transitions."""
        status_order = [
            InvoiceStatus.DRAFT,
            InvoiceStatus.ISSUED,
            InvoiceStatus.OVERDUE,
            InvoiceStatus.PAID,
            InvoiceStatus.CANCELLED,
        ]

        if old_status == new_status:
            return

        if old_status == InvoiceStatus.CANCELLED:
            raise ValidationError(_("Cannot change status of a cancelled invoice."))

        if old_status == InvoiceStatus.PAID and new_status != InvoiceStatus.CANCELLED:
            raise ValidationError(_("Cannot modify a paid invoice."))

        if status_order.index(new_status) < status_order.index(old_status) and new_status != InvoiceStatus.CANCELLED:
            raise ValidationError(_("Cannot move to a previous status."))

    def add_payment(self, amount: Decimal, payment_method: str, notes: str = "") -> 'Payment':
        """Record a payment against this invoice."""
        if self.status == InvoiceStatus.CANCELLED:
            raise ValidationError(_("Cannot add payment to cancelled invoice."))

        if amount <= 0:
            raise ValidationError(_("Payment amount must be positive."))

        from payments.models import Payment
        payment = Payment.objects.create(
            invoice=self,
            amount=amount,
            method=payment_method,
            currency=self.currency,
            notes=notes,
            processed_by=self.user,
            transaction_date=timezone.now()
        )

        self.mark_paid()

        # TODO: Maybe add some logic to check if the payment is completed
        payment.mark_completed()

        self.refresh_from_db()
        return payment
