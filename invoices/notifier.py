import logging

from django.urls import reverse

from common.models import CommonModel
from common.notifier import Notifier
from common.utils import send_email_notification
from invoices.enums import InvoiceStatus

logger = logging.getLogger(__name__)


class InvoiceNotifier(Notifier):
    def __init__(self, invoice, payment=None):
        super().__init__()
        self.invoice = invoice
        self.payment = payment

    def _get_common_context(self):
        """Return common context for all email templates."""
        context = super()._get_common_context()
        context.update({
            'invoice': self.invoice,
            'user': self.invoice.user,
            'invoice_url': f"{self.base_url}{reverse('invoice-detail', args=[self.invoice.id])}"
        })
        return context

    def _send_notification(self, subject_template, template_name, extra_context=None):
        """Helper method to send email notifications."""
        context = self._get_common_context()
        if extra_context:
            context.update(extra_context)

        subject = subject_template.format(
            self.invoice.invoice_number,
        )

        to_emails = [self.order.user.email]

        return send_email_notification(
            subject=subject,
            template_name=f'invoices/email/{template_name}',
            context=context,
            to_emails=to_emails
        )
    
    def send_invoice_issued_notification(self):
        """Send invoice issued notification to the user."""
        return self._send_notification(
            subject_template='Invoice {invoice_number} has been issued',
            template_name='invoice_issued',
            extra_context={
                'invoice_url': f"{self.base_url}{reverse('invoice-detail', args=[self.invoice.id])}",
            }
        )
    
    def send_invoice_overdue_notification(self):
        """Send invoice overdue notification to the user."""
        return self._send_notification(
            subject_template='Invoice {invoice_number} is overdue',
            template_name='invoice_overdue',
            extra_context={
                'invoice_url': f"{self.base_url}{reverse('invoice-detail', args=[self.invoice.id])}",
            }
        )
    
    def send_invoice_paid_notification(self):
        """Send invoice paid notification to the user."""
        if self.payment is None:
            logger.error("Payment is None for invoice paid notification")
            return False

        return self._send_notification(
            subject_template='Invoice {invoice_number} has been paid',
            template_name='payment_confirm',
            extra_context={
                'invoice_url': f"{self.base_url}{reverse('invoice-detail', args=[self.invoice.id])}",
                'recipient_name': f"{self.invoice.user.first_name} {self.invoice.user.last_name}",
                'payment_description': f"Payment for Invoice #{self.invoice.invoice_number}",
                'payment_method': self.payment.payment_method,
                'transaction_id': self.payment.payment_reference,
                'date': self.payment.date_created,
            }
        )
    
    def send_invoice_cancelled_notification(self):
        """Send invoice cancelled notification to the user."""
        return self._send_notification(
            subject_template='Invoice {invoice_number} has been cancelled',
            template_name='invoice_cancelled',
            extra_context={
                'invoice_url': f"{self.base_url}{reverse('invoice-detail', args=[self.invoice.id])}",
            }
        )

    def send_invoice_drafted_notification(self):
        """Send invoice drafted notification to the user."""
        return self._send_notification(
            subject_template='Invoice {invoice_number} has been drafted',
            template_name='invoice_drafted',
            extra_context={
                'invoice_url': f"{self.base_url}{reverse('invoice-detail', args=[self.invoice.id])}",
            }
        )


def notify_by_email(notification_type: str = None, notifier: InvoiceNotifier = None) -> bool:
    """
    Send a notification for the invoice.

    Args:
        notification_type: Type of notification to send (from InvoiceStatus)
        notifier: Instance of Notifier

    Returns:
        bool: True if notification was sent successfully, False otherwise

    Raises:
        ValueError: If notification_type is invalid
    """
    if notifier is None:
        logger.error("Notifier is None for refunds notifier notify_by_email()")
        return False

    try:
        if notification_type == InvoiceStatus.ISSUED:
            return notifier.send_invoice_issued_notification()
        elif notification_type == InvoiceStatus.PAID:
            return notifier.send_invoice_paid_notification()
        elif notification_type == InvoiceStatus.CANCELLED:
            return notifier.send_invoice_cancelled_notification()
        elif notification_type == InvoiceStatus.OVERDUE:
            return notifier.send_invoice_overdue_notification()
        elif notification_type == InvoiceStatus.DRAFT:
            return notifier.send_invoice_drafted_notification()
        else:
            error_msg = (
                f"Invalid notification type: {notification_type}. "
                f"Valid types are: {InvoiceStatus.PAID}, {InvoiceStatus.OVERDUE}, "
                f"{InvoiceStatus.ISSUED}, {InvoiceStatus.CANCELLED}, {InvoiceStatus.DRAFT}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
    except Exception as e:
        logger.error(f"Error sending refund notification: {str(e)}")
        return False