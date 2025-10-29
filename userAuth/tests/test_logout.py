from rest_framework import status


class TestLogout:
    """Test logout functionality."""

    def test_logout_authenticated(self, client, verified_user, logout_url):
        """Test logout when authenticated."""
        user, _, _, _ = verified_user
        client.force_authenticate(user=user)

        response = client.post(logout_url, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_logout_unauthenticated(self, client, logout_url):
        """Test logout without authentication."""
        response = client.post(logout_url, format='json')
        # Should still return 200 even if not authenticated
        assert response.status_code == status.HTTP_200_OK