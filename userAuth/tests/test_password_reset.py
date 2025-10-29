# tests/test_password_reset.py
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestPasswordReset:
    """Test password reset functionality."""

    def test_password_reset_request_valid_email(self, client, verified_user, password_reset_url):
        """Test requesting password reset with valid email."""
        user, _, _, _ = verified_user()
        data = {'email': user.email}

        response = client.post(password_reset_url, data, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'Email has been sent' in response.data['detail']

    def test_password_reset_request_invalid_email(self, client, password_reset_url):
        """Test requesting password reset with invalid email."""
        data = {'email': 'nonexistent@example.com'}

        response = client.post(password_reset_url, data, format='json')

        # Should still return 200 for security (don't reveal email existence)
        assert response.status_code == status.HTTP_200_OK

    def test_password_reset_confirm_valid(self, client, verified_user, password_reset_confirm_url):
        """Test password reset confirmation with valid token."""
        user, _, _, _ = verified_user()

        # Generate valid reset tokens
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        new_password = 'NewSecurePass123!'
        data = {
            'uid': uid,
            'token': token,
            'new_password1': new_password,
            'new_password2': new_password
        }

        response = client.post(password_reset_confirm_url, data, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'Password has been reset' in response.data['detail']

        # Verify new password works
        assert user.check_password(new_password) is False  # Old instance
        user.refresh_from_db()
        assert user.check_password(new_password) is True  # New instance

    def test_password_reset_confirm_invalid_token(self, client, verified_user, password_reset_confirm_url):
        """Test password reset with invalid token."""
        user, _, _, _ = verified_user()

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        data = {
            'uid': uid,
            'token': 'invalid-token',
            'new_password1': 'NewPass123!',
            'new_password2': 'NewPass123!'
        }

        response = client.post(password_reset_confirm_url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_reset_confirm_password_mismatch(self, client, verified_user, password_reset_confirm_url):
        """Test password reset with mismatched passwords."""
        user, _, _, _ = verified_user()

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        data = {
            'uid': uid,
            'token': token,
            'new_password1': 'NewPass123!',
            'new_password2': 'DifferentPass123!'  # Mismatch
        }

        response = client.post(password_reset_confirm_url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password' in response.data