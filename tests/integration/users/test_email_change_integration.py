import pytest
from unittest.mock import patch, Mock

from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator

from rest_framework import status


pytestmark = pytest.mark.django_db


class TestEmailChangeIntegration:
    """Integration tests for complete email change flow."""

    def test_complete_email_change_flow(self, authenticated_client, verified_user, email_change_request_url,
                                        email_change_confirm_url):
        """Test complete email change flow from request to confirmation."""
        user, _, _, _ = verified_user
        old_email = user.email
        new_email = 'completelynew@example.com'

        # Step 1: Request email change
        with patch('users.serializers.send_email_change_confirmation') as mock_send_confirmation:
            mock_send_confirmation.return_value = True

            request_data = {'new_email': new_email}
            response = authenticated_client.post(email_change_request_url, request_data)

            assert response.status_code == status.HTTP_200_OK
            mock_send_confirmation.assert_called_once()

        # Step 2: Confirm email change
        with patch('users.serializers.send_email_change_success_notification') as mock_send_notification:
            # Generate confirmation data
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            email_b64 = urlsafe_base64_encode(force_bytes(new_email))
            token = default_token_generator.make_token(user)

            confirm_url = email_change_confirm_url(uidb64, email_b64, token)
            response = authenticated_client.post(confirm_url)

            assert response.status_code == status.HTTP_200_OK

            # Verify changes
            user.refresh_from_db()
            assert user.email == new_email
            mock_send_notification.assert_called_once()