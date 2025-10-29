from rest_framework import status


class TestUserDetails:
    """Test user details retrieval and update."""

    def test_get_user_details_authenticated(self, client, verified_user, user_details_url):
        """Test retrieving user details when authenticated."""
        user, profile, _, _ = verified_user
        client.force_authenticate(user=user)

        response = client.get(user_details_url, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == user.email
        assert response.data['first_name'] == user.first_name
        assert response.data['last_name'] == user.last_name

    def test_update_user_details(self, client, verified_user, user_details_url):
        """Test updating user details."""
        user, _, _, _ = verified_user
        client.force_authenticate(user=user)

        data = {
            'first_name': 'UpdatedFirstName',
            'last_name': 'UpdatedLastName'
        }
        response = client.patch(user_details_url, data, format='json')
        assert response.status_code == status.HTTP_200_OK

        user.refresh_from_db()
        assert user.first_name == 'UpdatedFirstName'
        assert user.last_name == 'UpdatedLastName'

    def test_get_user_details_unauthenticated(self, client, user_details_url):
        """Test retrieving user details without authentication."""
        response = client.get(user_details_url, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED