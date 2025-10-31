import logging

import pytest
from django.core.management import call_command
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.contrib.auth import get_user_model
import random
import string


logger = logging.getLogger(__name__)
User = get_user_model()

def generate_valid_polish_phone_number():
    """Generate a valid Polish phone number for tests."""
    # Polish mobile numbers: +48 XXX XXX XXX
    prefixes = ['50', '51', '53', '57', '60', '66', '69', '72', '73', '78', '79', '88']
    prefix = random.choice(prefixes)
    number = ''.join(random.choices(string.digits, k=7))
    return f'+48{prefix}{number}'


@pytest.fixture(autouse=True)
def setup_site(db):
    """Ensure test site exists for allauth."""
    from django.contrib.sites.models import Site

    site, created = Site.objects.get_or_create(
        id=1,
        defaults={
            'domain': 'testserver',
            'name': 'Test Server'
        }
    )
    if not created:
        site.domain = 'testserver'
        site.name = 'Test Server'
        site.save()


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """Ensure clean database setup for tests."""
    with django_db_blocker.unblock():
        call_command('migrate', '--run-syncdb')


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """Enable database access for all tests."""
    pass


@pytest.fixture
def client():
    """Django test client fixture."""
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def authenticated_client(client, verified_user):
    """Create a client authenticated with a verified user."""
    user, _, _, _ = verified_user
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def test_image():
    """Create a test image for avatar uploads."""
    file = BytesIO()
    image = Image.new('RGB', (100, 100), color='red')
    image.save(file, 'JPEG')
    file.name = 'test.jpg'
    file.seek(0)
    return SimpleUploadedFile(
        name='test.jpg',
        content=file.read(),
        content_type='image/jpeg'
    )


@pytest.fixture
def login_url():
    return reverse('userAuth:rest_login')