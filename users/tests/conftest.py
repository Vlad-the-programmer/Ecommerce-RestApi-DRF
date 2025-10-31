from common.tests.conftest import *
# Used in tests
from userAuth.tests.conftest import verified_user, minimal_registration_data


@pytest.fixture
def user_details_url():
    # return reverse('userAuth:rest_user_details') # Use custom UserViewSet method instead
    return reverse('users:user-detail')

@pytest.fixture
def user_delete_profile_url():
    return reverse('users:user-delete-profile')
