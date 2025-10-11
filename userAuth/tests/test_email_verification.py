import pytest

from django.contrib.auth import get_user_model

from unittest.mock import patch
from rest_framework import status

from users.models import Profile

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestVerifyEmailView:
    """Test cases for VerifyEmailView."""

    def test_successful_email_verification(self, client, unverified_user, verify_email_url):
        """Test successful email verification."""
        user, profile, email_address, confirmation = unverified_user()

        data = {'key': confirmation.key}
        response = client.post(verify_email_url, data, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['detail'] == 'Email successfully verified. You can now log in.'

        # Refresh from database
        user.refresh_from_db()
        profile.refresh_from_db()
        email_address.refresh_from_db()

        # Check that user and profile are now active
        assert user.is_active is True
        assert profile.is_active is True
        assert email_address.verified is True

    def test_email_verification_invalid_key(self, client, verify_email_url):
        """Test email verification with invalid key."""
        data = {'key': 'invalid-key'}

        response = client.post(verify_email_url, data, format='json')

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'detail' in response.data

    def test_email_verification_missing_key(self, client, verify_email_url):
        """Test email verification with missing key."""
        response = client.post(verify_email_url, {}, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'key' in response.data

    @patch('userAuth.views.EmailConfirmationHMAC')
    def test_email_verification_exception_handling(self, mock_confirmation, client, verify_email_url):
        """Test exception handling during email verification."""
        mock_confirmation.objects.get.side_effect = Exception('Test error')

        data = {'key': 'any-key'}
        response = client.post(verify_email_url, data, format='json')

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert 'detail' in response.data
        assert 'An error occurred' in response.data['detail']

    def test_email_verification_already_verified(self, client, unverified_user, verify_email_url):
        """Test email verification for already verified email."""
        user, profile, email_address, confirmation = unverified_user()

        # Mark email as already verified
        email_address.verified = True
        email_address.save()

        data = {'key': confirmation.key}
        response = client.post(verify_email_url, data, format='json')

        # Should still return success
        assert response.status_code == status.HTTP_200_OK

    def test_email_verification_activates_correct_user(self, client, unverified_user, verify_email_url):
        """Test that verification activates the correct user."""
        user, profile, email_address, confirmation = unverified_user()

        # Create another user that should remain inactive
        other_user = User.objects.create_user(
            email='other@example.com',
            first_name='Other',
            last_name='User',
            password='password123',
            is_active=False
        )
        other_profile = Profile.objects.create(
            user=other_user,
            phone_number='+48987654321',
            date_of_birth='1995-01-01',
            is_active=False
        )

        data = {'key': confirmation.key}
        response = client.post(verify_email_url, data, format='json')

        assert response.status_code == status.HTTP_200_OK

        # Verify correct user is activated
        user.refresh_from_db()
        profile.refresh_from_db()
        other_user.refresh_from_db()
        other_profile.refresh_from_db()

        assert user.is_active is True
        assert profile.is_active is True
        assert other_user.is_active is False  # Other user should remain inactive
        assert other_profile.is_active is False