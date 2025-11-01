import logging

from rest_framework import status

from common.tests.conftest import authenticated_client

logger = logging.getLogger(__name__)


class TestUserDetails:
    """Test user details retrieval and update."""

    def test_get_user_details_authenticated(self, authenticated_client, verified_user, user_details_url):
        """Test retrieving user details when authenticated."""
        user, profile, _, _ = verified_user

        response = authenticated_client.get(user_details_url(profile.uuid), format='json')

        # Debug the response
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response data keys: {list(response.data.keys()) if response.data else 'No data'}")
        logger.debug(f"Full response data: {response.data}")

        assert response.status_code == status.HTTP_200_OK

        # Check that email field exists in response
        assert 'email' in response.data
        assert response.data['email'] == user.email

        # Check other expected fields
        assert 'first_name' in response.data
        assert 'last_name' in response.data
        assert response.data['first_name'] == user.first_name
        assert response.data['last_name'] == user.last_name

    def test_update_user_details(self, authenticated_client, verified_user, user_details_url):
        """Test updating user details."""
        user, profile, _, _ = verified_user

        data = {
            'first_name': 'UpdatedFirstName',
            'last_name': 'UpdatedLastName'
        }

        logger.debug(f"Before update - User first_name: {user.first_name}")
        logger.debug(f"Update data: {data}")

        response = authenticated_client.patch(user_details_url(profile.uuid), data, format='json')

        logger.debug(f"Update response status: {response.status_code}")
        logger.debug(f"Update response data: {response.data}")

        assert response.status_code == status.HTTP_200_OK

        # Refresh user from database
        user.refresh_from_db()
        logger.debug(f"After update - User first_name: {user.first_name}")

        # Verify the update
        assert user.first_name == 'UpdatedFirstName'
        assert user.last_name == 'UpdatedLastName'

        # Also verify the response contains updated data
        assert response.data['first_name'] == 'UpdatedFirstName'
        assert response.data['last_name'] == 'UpdatedLastName'

    def test_update_profile_fields(self, authenticated_client, verified_user, user_details_url):
        """Test updating profile-specific fields."""
        user, profile, _, _ = verified_user

        data = {
            'gender': 'female',
            'country': 'GB',
            'phone_number': '+48123456789'
        }

        response = authenticated_client.patch(user_details_url(profile.uuid), data, format='json')
        assert response.status_code == status.HTTP_200_OK

        # Refresh profile from database
        profile.refresh_from_db()

        # Verify the update
        assert profile.gender == 'female'
        assert profile.country == 'GB'
        assert profile.phone_number == '+48123456789'