from typing import Any

from django.conf import settings


class Notifier:
    def __init__(self):
        self.site_name = getattr(settings, 'SITE_NAME', 'E-commerce Site')
        self.site_url = getattr(settings, 'SITE_URL', 'https://your-ecommerce-site.com')
        self.base_url = getattr(settings, 'SITE_URL', 'https://your-ecommerce-site.com')
        self.unsubscribe_url = getattr(settings, 'UNSUBSCRIBE_URL', 'https://your-ecommerce-site.com/unsubscribe')

    def _get_common_context(self) -> dict[str, Any]:
        """Return common context for all email templates."""
        return {
            'site_name': self.site_name,
            'site_url': self.site_url,
            'unsubscribe_url': self.unsubscribe_url,
        }

    def _send_notification(self, subject_template, template_name, extra_context=None) -> bool:
        """Helper method to send email notifications."""
        pass
