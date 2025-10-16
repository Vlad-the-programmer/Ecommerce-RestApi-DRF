from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _


class OrderStatuses(TextChoices):
    PENDING = "pending", _("Pending")
    PAID = "paid", _("Paid")
    UNPAID = "unpaid", _("Unpaid")
    SHIPPED = "shipped", _("Shipped")
    DELIVERED = "delivered", _("Delivered")
    CANCELLED = "cancelled", _("Cancelled")
    REFUNDED = "refunded", _("Refunded")