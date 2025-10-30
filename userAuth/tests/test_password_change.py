import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestPasswordChange:
    """Test password change functionality."""

    def test_password_change_authenticated(self, authenticated_client, password_change_url):
        """Test password change when authenticated."""
        data = {
            'old_password': 'password123',  # From verified_user fixture
            'new_password1': 'NewSecurePass456!',
            'new_password2': 'NewSecurePass456!'
        }

        response = authenticated_client.post(password_change_url, data, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'New password has been saved' in response.data['detail']

    def test_password_change_unauthenticated(self, client, password_change_url):
        """Test password change without authentication."""
        data = {
            'old_password': 'oldpass',
            'new_password1': 'newpass',
            'new_password2': 'newpass'
        }

        response = client.post(password_change_url, data, format='json')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_password_change_wrong_old_password(self, authenticated_client, password_change_url):
        """Test password change with incorrect old password."""
        data = {
            'old_password': 'wrong-old-password',
            'new_password1': 'NewSecurePass456!',
            'new_password2': 'NewSecurePass456!'
        }

        response = authenticated_client.post(password_change_url, data, format='json')

        # Should return 400 with old_password error
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'old_password' in response.data
        assert 'Invalid old password' in str(response.data['old_password'])