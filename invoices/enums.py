from django.utils.translation import gettext_lazy as _
from django.db.models import TextChoices


class InvoiceStatus(TextChoices):
    DRAFT = "DRAFT", _("Draft")
    ISSUED = "ISSUED", _("Issued")
    PAID = "PAID", _("Paid")
    CANCELLED = "CANCELLED", _("Cancelled")
    OVERDUE = "OVERDUE", _("Overdue")