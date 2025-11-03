import uuid

from common.tests.conftest import *

# Used in tests
from userAuth.tests.conftest import (verified_user, minimal_registration_data,
                                     existing_user, admin_user, multiple_verified_users,
                                     )


@pytest.fixture
def user_details_url():
    # return reverse('userAuth:rest_user_details') # Use custom UserViewSet method instead
    def _get_url(pk:uuid.UUID=None):
        if pk is None:
            return ""
        return reverse('users:user-detail', kwargs={'pk': pk})
    return _get_url

@pytest.fixture
def user_delete_profile_url():
    def _get_url(pk: uuid.UUID = None):
        if pk is None:
            return ""
        return reverse('users:user-delete-profile', kwargs={'pk': pk})

    return _get_url

@pytest.fixture
def user_list_url():
    """URL for user list endpoint."""
    return reverse('users:user-list')
