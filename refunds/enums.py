from django.utils.translation import gettext_lazy as _
from django.db.models import TextChoices


class RefundStatus(TextChoices):
    PENDING = 'pending', _('Pending')
    PROCESSING = 'processing', _('Processing')
    APPROVED = 'approved', _('Approved')
    COMPLETED = 'completed', _('Completed')
    REJECTED = 'rejected', _('Rejected')
    CANCELLED = 'cancelled', _('Cancelled')


class RefundReason(TextChoices):
    CUSTOMER_REQUEST = 'customer_request', _('Customer Request')
    DEFECTIVE_PRODUCT = 'defective_product', _('Defective Product')
    WRONG_ITEM = 'wrong_item', _('Wrong Item Received')
    DAMAGED = 'damaged', _('Damaged During Shipping')
    LATE_DELIVERY = 'late_delivery', _('Late Delivery')
    QUALITY_ISSUE = 'quality_issue', _('Quality Issue')
    SIZE_ISSUE = 'size_issue', _('Size Doesn\'t Fit')
    OTHER = 'other', _('Other')


class RefundMethod(TextChoices):
    ORIGINAL_PAYMENT = 'original_payment', _('Original Payment Method')
    STORE_CREDIT = 'store_credit', _('Store Credit')
    BANK_TRANSFER = 'bank_transfer', _('Bank Transfer')
    GIFT_CARD = 'gift_card', _('Gift Card')