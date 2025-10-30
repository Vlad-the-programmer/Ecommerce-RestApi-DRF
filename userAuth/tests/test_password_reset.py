import pytest
import logging
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.django_db


class TestPasswordReset:
    """Test password reset functionality."""

    def test_password_reset_request_valid_email(self, client, verified_user, password_reset_url):
        """Test requesting password reset with valid email."""
        user, _, _, _ = verified_user
        data = {'email': user.email}

        response = client.post(password_reset_url, data, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'Password reset e-mail has been sent.' in response.data['detail']

    def test_password_reset_request_invalid_email(self, client, password_reset_url):
        """Test requesting password reset with invalid email."""
        data = {'email': 'nonexistent@example.com'}

        response = client.post(password_reset_url, data, format='json')

        # Should still return 200 for security (don't reveal email existence)
        assert response.status_code == status.HTTP_200_OK

    def test_password_reset_confirm_valid(self, client, verified_user, password_reset_confirm_url):
        """Test password reset confirmation with valid token."""
        user, _, _, _ = verified_user

        # Generate valid reset tokens - ensure proper encoding
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        new_password = 'NewSecurePass123!'
        data = {
            'uid': uid,
            'token': token,
            'new_password1': new_password,
            'new_password2': new_password
        }

        logger.debug("Password reset attempt - User: %s, UID: %s, Token: %s",
                     user.email, uid, token)

        response = client.post(password_reset_confirm_url, data, format='json')

        logger.debug("Password reset response - Status: %s, Data: %s",
                     response.status_code, response.data)

        # Should return 200 for successful reset
        assert response.status_code == status.HTTP_200_OK
        assert 'Password has been reset' in response.data['detail']

        # Verify new password works
        user.refresh_from_db()
        password_changed = user.check_password(new_password)
        logger.debug("Password change verification: %s", password_changed)
        assert password_changed is True

    def test_password_reset_confirm_invalid_token(self, client, verified_user, password_reset_confirm_url):
        """Test password reset with invalid token."""
        user, _, _, _ = verified_user

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        data = {
            'uid': uid,
            'token': 'invalid-token',
            'new_password1': 'NewPass123!',
            'new_password2': 'NewPass123!'
        }

        logger.debug("Invalid token reset attempt - User: %s, UID: %s", user.email, uid)

        response = client.post(password_reset_confirm_url, data, format='json')

        logger.debug("Invalid token response - Status: %s, Data: %s",
                     response.status_code, response.data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_reset_confirm_password_mismatch(self, client, verified_user, password_reset_confirm_url):
        """Test password reset with mismatched passwords."""
        user, _, _, _ = verified_user

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        data = {
            'uid': uid,
            'token': token,
            'new_password1': 'NewPass123!',
            'new_password2': 'DifferentPass123!'  # Mismatch
        }

        logger.debug("Password mismatch reset attempt - User: %s, UID: %s", user.email, uid)

        response = client.post(password_reset_confirm_url, data, format='json')

        logger.debug("Password mismatch response - Status: %s, Data: %s",
                     response.status_code, response.data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'new_password2' in response.data
        assert "didn't match" in str(response.data['new_password2'])

    def test_password_reset_debug_uid_encoding(self, client, verified_user):
        """Debug method to check UID encoding/decoding."""
        user, _, _, _ = verified_user

        # Generate UID the same way Django does
        from django.utils.http import urlsafe_base64_decode
        from django.utils.encoding import force_str

        uid = urlsafe_base64_encode(force_bytes(user.pk))

        logger.debug("UID Encoding Debug - User PK: %s", user.pk)
        logger.debug("UID Encoding Debug - Force bytes: %s", force_bytes(user.pk))
        logger.debug("UID Encoding Debug - UID encoded: %s", uid)

        # Try to decode it back
        try:
            decoded_uid = force_str(urlsafe_base64_decode(uid))
            logger.debug("UID Encoding Debug - UID decoded: %s", decoded_uid)
            logger.debug("UID Encoding Debug - Match: %s", decoded_uid == str(user.pk))
        except Exception as e:
            logger.error("UID Encoding Debug - Decode error: %s", e)