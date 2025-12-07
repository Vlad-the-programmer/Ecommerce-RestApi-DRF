import logging

from django.urls import reverse

from common.notifier import Notifier
from common.utils import send_email_notification
from orders.enums import OrderStatuses

logger = logging.getLogger(__name__)


class OrderNotifier(Notifier):
    def __init__(self, order):
        self.order = order
        super().__init__()

    def _get_common_context(self):
        """Return common context for all email templates."""
        context = super()._get_common_context()
        context.update({
            'order': self.order,
            'user': self.order.user,
            'order_url': f"{self.base_url}{reverse('order-detail', args=[self.order.uuid])}"
        })
        return context

    def _send_notification(self, subject_template, template_name, extra_context=None):
        """Helper method to send email notifications."""
        context = self._get_common_context()
        if extra_context:
            context.update(extra_context)

        subject = subject_template.format(
            self.order.order_number,
        )

        to_emails = [self.order.user.email]

        return send_email_notification(
            subject=subject,
            template_name=f'orders/email/{template_name}',
            context=context,
            to_emails=to_emails
        )

    def send_order_placed_notification(self):
        """Send notification when order is placed."""
        return self._send_notification(
            subject_template="Order Placed #{}",
            template_name='order_placed'
        )

    def send_order_updated_notification(self):
        """Send notification when order is updated."""
        return self._send_notification(
            subject_template="Order Updated #{}",
            template_name='order_updated'
        )

    def send_order_cancelled_notification(self):
        """Send notification when order is cancelled."""
        return self._send_notification(
            subject_template="Order Cancelled #{}",
            template_name='order_cancelled'
        )

    def send_order_completed_notification(self):
        """Send notification when order is completed."""
        return self._send_notification(
            subject_template="Order Completed #{}",
            template_name='order_completed'
        )

    def send_order_refunded_notification(self):
        """Send notification when order is refunded."""
        return self._send_notification(
            subject_template="Order Refunded #{}",
            template_name='order_refunded'
        )

    def send_order_paid_notification(self):
        """Send notification when order is paid."""
        return self._send_notification(
            subject_template="Order Paid #{}",
            template_name='order_paid'
        )

    def send_order_unpaid_notification(self):
        """Send notification when order is paid."""
        return self._send_notification(
            subject_template="Order Unpaid #{}",
            template_name='order_unpaid'
        )

    def send_order_shipped_notification(self):
        """Send notification when order is shipped."""
        return self._send_notification(
            subject_template="Order Shipped #{}",
            template_name='order_shipped'
        )

    def send_order_delivered_notification(self):
        """Send notification when order is delivered."""
        return self._send_notification(
            subject_template="Order Delivered #{}",
            template_name='order_delivered'
        )

    def send_order_returned_notification(self):
        """Send notification when order is returned."""
        return self._send_notification(
            subject_template="Order Returned #{}",
            template_name='order_returned'
        )


def notify_by_email(notification_type: str = None, notifier: OrderNotifier = None) -> bool:
    """
    Send a notification for the order.

    Args:
        notification_type: Type of notification to send (from OrderStatus)
        notifier: Instance of OrderNotifier

    Returns:
        bool: True if notification was sent successfully, False otherwise

    Raises:
        ValueError: If notification_type is invalid
    """

    if notifier is None:
        logger.error("Notifier is None for orders notifier send_notification()")
        return False

    try:
        if notification_type == OrderStatuses.APPROVED:
            notifier.send_order_placed_notification()
        elif notification_type == OrderStatuses.UPDATED:
            notifier.send_order_updated_notification()
        elif notification_type == OrderStatuses.CANCELLED:
            notifier.send_order_cancelled_notification()
        elif notification_type == OrderStatuses.COMPLETED:
            notifier.send_order_completed_notification()
        elif notification_type == OrderStatuses.REFUNDED:
            notifier.send_order_refunded_notification()
        elif notification_type == OrderStatuses.PAID:
            notifier.send_order_paid_notification()
        elif notification_type == OrderStatuses.UNPAID:
            notifier.send_order_unpaid_notification()
        elif notification_type == OrderStatuses.SHIPPED:
            notifier.send_order_shipped_notification()
        elif notification_type == OrderStatuses.DELIVERED:
            notifier.send_order_delivered_notification()
        elif notification_type == OrderStatuses.RETURNED:
            notifier.send_order_returned_notification()
        else:
            error_msg = (
                f"Invalid notification type: {notification_type}. "
                f"Valid types are: {OrderStatuses.APPROVED}, {OrderStatuses.UPDATED}, "
                f"{OrderStatuses.CANCELLED}, {OrderStatuses.COMPLETED}, "
                f"{OrderStatuses.REFUNDED}, {OrderStatuses.PAID}, "
                f"{OrderStatuses.UNPAID}, {OrderStatuses.SHIPPED}, "
                f"{OrderStatuses.DELIVERED}, {OrderStatuses.RETURNED}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        return True
    except Exception as e:
        logger.error(f"Error sending order notification: {str(e)}")
        return False