import pytest
from django.contrib.auth import get_user_model
from unittest.mock import patch
from rest_framework import status
from allauth.account.models import EmailConfirmation

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

        # This might return 201 or 200 depending on your implementation
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

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

    def test_email_verification_missing_key(self, client, verify_email_url):
        """Test email verification with missing key."""
        response = client.post(verify_email_url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch('allauth.account.models.EmailConfirmation.objects.get')
    def test_email_verification_exception_handling(self, mock_get, client, verify_email_url):
        """Test exception handling during email verification."""
        mock_get.side_effect = Exception('Test error')

        data = {'key': 'any-key'}
        response = client.post(verify_email_url, data, format='json')
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_email_verification_already_verified(self, client, unverified_user, verify_email_url):
        """Test email verification for already verified email."""
        user, profile, email_address, confirmation = unverified_user()

        # Mark email as already verified
        email_address.verified = True
        email_address.save()

        data = {'key': confirmation.key}
        response = client.post(verify_email_url, data, format='json')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

    def test_email_verification_activates_correct_user(self, client, unverified_user, verify_email_url):
        """Test that verification activates the correct user."""
        user, profile, email_address, confirmation = unverified_user()

        # Create another user with unique phone number
        other_user = User.objects.create_user(
            email='other@example.com',
            first_name='Other',
            last_name='User',
            password='password123',
            is_active=False
        )
        other_profile = Profile.objects.create(
            user=other_user,
            phone_number='+48123456780',  # Different phone number
            date_of_birth='1995-01-01',
            is_active=False
        )

        data = {'key': confirmation.key}
        response = client.post(verify_email_url, data, format='json')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

        # Verify correct user is activated
        user.refresh_from_db()
        profile.refresh_from_db()
        other_user.refresh_from_db()
        other_profile.refresh_from_db()

        assert user.is_active is True
        assert profile.is_active is True
        assert other_user.is_active is False
        assert other_profile.is_active is False