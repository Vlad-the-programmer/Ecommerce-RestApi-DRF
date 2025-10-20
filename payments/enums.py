from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentMethod(models.TextChoices):
    CREDIT_CARD = "CREDIT_CARD", _("Credit Card")
    BANK_TRANSFER = "BANK_TRANSFER", _("Bank Transfer")
    PAYPAL = "PAYPAL", _("PayPal")
    CASH = "CASH", _("Cash")
    OTHER = "OTHER", _("Other")


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    COMPLETED = "COMPLETED", _("Completed")
    FAILED = "FAILED", _("Failed")
    REFUNDED = "REFUNDED", _("Refunded")
    CANCELLED = "CANCELLED", _("Cancelled")