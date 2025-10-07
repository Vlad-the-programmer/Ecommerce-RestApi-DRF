from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.contrib.sites.models import Site
from django.utils.translation import gettext_lazy as _


def send_confirmation_email(user, request):
    """Send a confirmation email to the user."""

    try:
        # Generate token for email confirmation
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        # Get or create default site
        try:
            site = Site.objects.get_current(request)
            domain = site.domain
            site_name = site.name
        except Exception:
            # Fallback to default values if site is not configured
            domain = getattr(settings, 'SITE_DOMAIN', 'localhost:8000')
            site_name = getattr(settings, 'SITE_NAME', 'Your Site')

        # Prepare email context
        protocol = 'https' if request.is_secure() else 'http'
        
        # Clean up the domain
        domain = domain.split('://')[-1].split('/')[0]  # Remove protocol and path if present
        
        # Get the port from the request
        port = request.get_port()
        
        # Construct the base URL
        base_url = f'{protocol}://{domain}'
        
        # Add port if it's non-standard
        if port and port not in ['80', '443'] and ':' not in domain:
            base_url = f'{base_url}:{port}'
            
        # Construct the verification URL with UID and token in the path
        verify_path = f'/api/auth/dj_rest_auth/registration/verify-email/confirm/{uid}/{token}/'
        activate_url = f'{base_url}{verify_path}'

        message = render_to_string(
            'account/email/email_confirmation_message.txt',
            {
            'user': user,
            'domain': domain,
            'site_name': site_name,
            'activate_url': activate_url
        })

        # Prepare email subject - strip any whitespace from the rendered template
        subject = render_to_string(
            'account/email/email_confirmation_subject.txt',
            {
                'site_name': site_name
            }
        ).strip()  # Remove any leading/trailing whitespace including newlines

        # Send email
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in send_confirmation_email: {str(e)}", exc_info=True)
        return False


    
    