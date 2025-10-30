from common.tests.conftest import *


@pytest.fixture
def user_details_url():
    return reverse('userAuth:rest_user_details')