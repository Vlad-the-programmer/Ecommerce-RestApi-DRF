from rest_framework import status


class TestTokenVerification:
    """Test token verification endpoints."""

    def test_token_verify_valid(self, client, verified_user, token_verify_url):
        """Test verifying a valid token."""
        user, _, _, _ = verified_user
        client.force_authenticate(user=user)

        # Get a valid token first
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=user)

        data = {'token': token.key}
        response = client.post(token_verify_url, data, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_token_verify_invalid(self, client, token_verify_url):
        """Test verifying an invalid token."""
        data = {'token': 'invalid-token'}
        response = client.post(token_verify_url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST