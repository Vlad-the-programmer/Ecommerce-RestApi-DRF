import pytest
from django.core.management import call_command
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.contrib.auth import get_user_model
from allauth.account.models import EmailConfirmation, EmailAddress
import random
import string

from users.models import Profile


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
def existing_user():
    """Create an existing user for duplicate tests."""

    def _create_user(email='existing@example.com', phone_number=None):
        if phone_number is None:
            phone_number = generate_valid_polish_phone_number()

        user = User.objects.create_user(
            email=email,
            first_name='Existing',
            last_name='User',
            password='password123'
        )
        Profile.objects.create(
            user=user,
            phone_number=phone_number,
            date_of_birth='1990-01-01'
        )
        return user

    return _create_user


@pytest.fixture
def unverified_user():
    """Create an unverified user with email confirmation."""

    def _create_user():
        user = User.objects.create_user(
            email='unverified@example.com',
            first_name='Unverified',
            last_name='User',
            password='password123',
            is_active=False
        )
        profile = Profile.objects.create(
            user=user,
            phone_number=generate_valid_polish_phone_number(),  # Fixed: valid phone number
            date_of_birth='1995-01-01',
            is_active=False
        )
        email_address = EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=False
        )
        confirmation = EmailConfirmation.objects.create(
            email_address=email_address
        )
        return user, profile, email_address, confirmation

    return _create_user


@pytest.fixture
def login_url():
    return reverse('userAuth:rest_login')