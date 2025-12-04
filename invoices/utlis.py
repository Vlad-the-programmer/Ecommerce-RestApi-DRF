import logging

from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils.html import strip_tags


logger = logging.getLogger(__name__)


def send_email_confirmation(
        subject,
        template_name,
        context,
        to_emails,
        from_email=None,
        bcc=None,
        reply_to=None,
        attachments=None
):
    """
    Send an email using a template.

    Args:
        subject (str): Email subject
        template_name (str): Path to the template file (without .html/.txt extension)
        context (dict): Context variables for the template
        to_emails (list): List of recipient email addresses
        from_email (str, optional): Sender email address. Defaults to settings.DEFAULT_FROM_EMAIL.
        bcc (list, optional): List of BCC email addresses. Defaults to None.
        reply_to (list, optional): List of reply-to email addresses. Defaults to None.
        attachments (list, optional): List of (filename, content, mimetype) tuples. Defaults to None.

    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    if not from_email:
        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@your-ecommerce-site.com')

    html_content = render_to_string(f'{template_name}.html', context)

    text_content = strip_tags(html_content)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email,
        to=to_emails,
        bcc=bcc or [],
        reply_to=reply_to or [from_email]
    )

    msg.attach_alternative(html_content, "text/html")

    if attachments:
        for filename, content, mimetype in attachments:
            msg.attach(filename, content, mimetype)

    try:
        msg.send()
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False