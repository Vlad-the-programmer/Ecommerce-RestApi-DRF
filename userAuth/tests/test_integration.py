import pytest
from allauth.account.models import EmailAddress, EmailConfirmation
from django.core import mail

from django.contrib.auth import get_user_model

from rest_framework import status


User = get_user_model()

pytestmark = pytest.mark.django_db


class TestIntegrationFlow:
    """Integration tests for the complete registration and verification flow."""

    def test_complete_registration_verification_login_flow(self, client, minimal_registration_data, register_url,
                                                           verify_email_url, login_url):
        """Test complete flow: registration -> email verification -> login."""
        # Step 1: Register
        response = client.post(register_url, minimal_registration_data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        # Step 2: Extract verification key from email
        assert len(mail.outbox) == 1
        user = User.objects.get(email='test@example.com')
        email_address = EmailAddress.objects.get(email=user.email)
        confirmation = EmailConfirmation.objects.get(email_address=email_address)

        # Step 3: Verify email
        verify_data = {'key': confirmation.key}
        response = client.post(verify_email_url, verify_data, format='json')
        assert response.status_code == status.HTTP_200_OK

        # Step 4: Login with verified account
        login_data = {
            'email': 'test@example.com',
            'password': 'SecurePass123!'
        }
        response = client.post(login_url, login_data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'key' in response.data  # Should return auth token

    def test_login_before_verification_fails(self, client, minimal_registration_data, register_url, login_url):
        """Test that login fails before email verification."""
        # Register but don't verify
        response = client.post(register_url, minimal_registration_data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        # Try to login
        login_data = {
            'email': 'test@example.com',
            'password': 'SecurePass123!'
        }
        response = client.post(login_url, login_data, format='json')

        # Should fail because account is not active
        assert response.status_code == status.HTTP_400_BAD_REQUEST