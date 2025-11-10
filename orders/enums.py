from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _


class OrderStatuses(TextChoices):
    PENDING = "pending", _("Pending")
    APPROVED = "approved", _("Approved")
    PAID = "paid", _("Paid")
    UNPAID = "unpaid", _("Unpaid")
    SHIPPED = "shipped", _("Shipped")
    DELIVERED = "delivered", _("Delivered")
    CANCELLED = "cancelled", _("Cancelled")
    REFUNDED = "refunded", _("Refunded")
    COMPLETED = "completed", _("Completed")