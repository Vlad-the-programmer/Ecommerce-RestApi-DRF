import logging

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.contrib.sites.models import Site


logger = logging.getLogger(__name__)


def get_site_info(request) -> tuple[str, str]:
    """Get site information."""
    try:
        site = Site.objects.get_current(request)
        domain = site.domain
        site_name = site.name
    except Exception:
        domain = getattr(settings, 'SITE_DOMAIN', 'localhost:8000')
        site_name = getattr(settings, 'SITE_NAME', 'EcommerceRestApi')
    return domain, site_name


def send_email_change_confirmation(user, new_email: str, request) -> bool:
    """Send a confirmation email for email change request."""

    try:
        # Generate token for email change confirmation
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        email_b64 = urlsafe_base64_encode(force_bytes(new_email))

        # Get site information
        domain, site_name = get_site_info(request)

        # Prepare URL components
        protocol = 'https' if request.is_secure() else 'http'
        domain = domain.split('://')[-1].split('/')[0]

        # Construct base URL with port if needed
        port = request.get_port()
        base_url = f'{protocol}://{domain}'
        if port and port not in ['80', '443'] and ':' not in domain:
            base_url = f'{base_url}:{port}'

        # Construct the email change confirmation URL
        confirm_path = reverse('users:email_change_confirm', args=[uid, email_b64, token])
        confirm_url = f'{base_url}{confirm_path}'

        # Prepare email context
        context = {
            'user': user,
            'new_email': new_email,
            'current_email': user.email,
            'domain': domain,
            'site_name': site_name,
            'confirm_url': confirm_url,
        }

        # Render email subject
        subject = render_to_string(
            'account/email/email_change_confirmation_subject.html',
            context
        ).strip()

        # Render HTML email
        html_message = render_to_string(
            'account/email/email_change_confirmation_message.html',
            context
        )

        # Render plain text fallback
        plain_message = render_to_string(
            'account/email/email_change_confirmation_message.txt',
            context
        )

        # Send email to the NEW email address
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            recipient_list=[new_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Email change confirmation sent to {new_email} for user {user.username}")
        return True

    except Exception as e:
        logger.error(f"Error sending email change confirmation: {str(e)}", exc_info=True)
        return False


def send_email_change_success_notification(user, old_email, new_email, request):
    """Send a success notification after email change."""

    try:
        # Get site information
        domain, site_name = get_site_info(request)

        # Prepare email context
        context = {
            'user': user,
            'old_email': old_email,
            'new_email': new_email,
            'domain': domain,
            'site_name': site_name,
        }

        # Render email subject
        subject = render_to_string(
            'account/email/email_change_success_notification_subject.txt',
            context
        ).strip()

        # Render HTML email
        html_message = render_to_string(
            'account/email/email_change_success_notification.html',
            context
        )

        # Render plain text fallback
        plain_message = render_to_string(
            'account/email/email_change_success_notification.txt',
            context
        )

        # Send email to the NEW email address
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            recipient_list=[new_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Email change success notification sent to {new_email} for user {user.username}")
        return True

    except Exception as e:
        logger.error(f"Error sending email change success notification: {str(e)}", exc_info=True)
        return False