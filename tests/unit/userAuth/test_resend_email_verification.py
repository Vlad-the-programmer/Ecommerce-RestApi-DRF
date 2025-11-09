from rest_framework import status


class TestResendVerification:
    """Test resending email verification."""

    def test_resend_verification_unverified(self, client, unverified_user, resend_verification_url):
        """Test resending verification for unverified user."""
        user, _, _, _ = unverified_user

        data = {'email': user.email}
        response = client.post(resend_verification_url, data, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_resend_verification_already_verified(self, client, verified_user, resend_verification_url):
        """Test resending verification for already verified user."""
        user, _, _, _ = verified_user

        data = {'email': user.email}
        response = client.post(resend_verification_url, data, format='json')
        # Should still return 200 but might not send email
        assert response.status_code == status.HTTP_200_OK

    def test_resend_verification_nonexistent_email(self, client, resend_verification_url):
        """Test resending verification for non-existent email."""
        data = {'email': 'nonexistent@example.com'}
        response = client.post(resend_verification_url, data, format='json')
        # Should still return 200 for security reasons (don't reveal if email exists)
        assert response.status_code == status.HTTP_200_OK