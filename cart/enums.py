from django.utils.translation import gettext_lazy as _
from django.db import models


class CART_STATUSES(models.TextChoices):
    ACTIVE = "active", _("Active")
    ABANDONED = "abandoned", _("Abandoned")
    PAID = "paid", _("Paid")
    REFUNDED = "refunded", _("Refunded")
    CANCELLED = "cancelled", _("Cancelled")