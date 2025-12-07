import logging

from django.conf import settings
from django.urls import reverse

from common.notifier import Notifier
from common.utils import send_email_notification
from refunds.enums import RefundStatus

logger = logging.getLogger(__name__)


class RefundNotifier(Notifier):
    def __init__(self, refund):
        self.refund = refund
        super().__init__()

    def _get_common_context(self) -> dict:
        """Return common context for all email templates."""
        context = super()._get_common_context()
        context.update({
            'refund': self.refund,
            'order': self.refund.order,
            'user': self.refund.order.user,
            'site_name': self.site_name,
            'refund_url': f"{self.base_url}{reverse('refund-detail', args=[self.refund.id])}"
        })
        return context

    def _send_notification(self, subject_template, template_name, extra_context=None) -> bool:
        """Helper method to send email notifications."""
        context = self._get_common_context()
        if extra_context:
            context.update(extra_context)

        subject = subject_template.format(
            self.refund.order.order_number,
        )

        to_emails = [self.refund.order.user.email]
        
        return send_email_notification(
            subject=subject,
            template_name=f'refunds/email/{template_name}',
            context=context,
            to_emails=to_emails
        )

    def send_approval_notification(self):
        """Send notification when refund is approved."""
        return self._send_notification(
            subject_template="Refund Approved for Order #{}",
            template_name='refund_approved'
        )

    def send_rejection_notification(self):
        """Send notification when refund is rejected."""
        return self._send_notification(
            subject_template="Refund Rejected for Order #{}",
            template_name='refund_rejected',
            extra_context={
                'rejection_reason': self.refund.rejection_reason or 'No reason provided.'
            }
        )

    def send_cancellation_notification(self):
        """Send notification when refund is cancelled."""
        return self._send_notification(
            subject_template="Refund Cancelled for Order #{}",
            template_name='refund_cancelled',
            extra_context={
                'cancellation_reason': self.refund.cancellation_reason or 'No reason provided.'
            }
        )

    def send_completion_notification(self):
        """Send notification when refund is completed."""
        return self._send_notification(
            subject_template="Refund Processed for Order #{}",
            template_name='refund_completed',
            extra_context={
                'amount_refunded': self.refund.amount,
                'refund_method': self.refund.payment_method or 'original payment method'
            }
        )


def notify_by_email(notification_type: str = None, notifier: RefundNotifier = None) -> bool:
    """
    Send a notification for the refund.
    
    Args:
        notification_type: Type of notification to send (from RefundStatus)
        notifier: Instance of RefundNotifier
        
    Returns:
        bool: True if notification was sent successfully, False otherwise
        
    Raises:
        ValueError: If notification_type is invalid
    """
    if notifier is None:
        logger.error("Notifier is None for refunds notifier notify_by_email()")
        return False

    try:
        if notification_type == RefundStatus.APPROVED:
            return notifier.send_approval_notification()
        elif notification_type == RefundStatus.REJECTED:
            return notifier.send_rejection_notification()
        elif notification_type == RefundStatus.CANCELLED:
            return notifier.send_cancellation_notification()
        elif notification_type == RefundStatus.COMPLETED:
            return notifier.send_completion_notification()
        else:
            error_msg = (
                f"Invalid notification type: {notification_type}. "
                f"Valid types are: {RefundStatus.APPROVED}, {RefundStatus.REJECTED}, "
                f"{RefundStatus.CANCELLED}, {RefundStatus.COMPLETED}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
    except Exception as e:
        logger.error(f"Error sending refund notification: {str(e)}")
        return False