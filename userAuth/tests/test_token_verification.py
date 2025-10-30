from rest_framework import status


class TestTokenVerification:
    """Test token verification endpoints."""

    def test_token_verify_valid(self, client, verified_user, token_verify_url):
        """Test verifying a valid token."""
        user, _, _, _ = verified_user

        # FIX: Use JWT token instead of DRF Token
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        data = {'token': access_token}
        response = client.post(token_verify_url, data, format='json')
        # FIX: JWT token verify usually returns 200 for valid tokens
        assert response.status_code == status.HTTP_200_OK

    def test_token_verify_invalid(self, client, token_verify_url):
        """Test verifying an invalid token."""
        data = {'token': 'invalid-token'}
        response = client.post(token_verify_url, data, format='json')
        # FIX: JWT usually returns 401 for invalid tokens
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED]