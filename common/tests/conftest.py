import pytest
import os
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.contrib.auth import get_user_model
from allauth.account.models import EmailConfirmation, EmailAddress

from users.models import Profile, Gender

User = get_user_model()


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
def valid_registration_data():
    """Valid registration data fixture."""
    return {
        'email': 'test@example.com',
        'first_name': 'John',
        'last_name': 'Doe',
        'password1': 'SecurePass123!',
        'password2': 'SecurePass123!',
        'gender': Gender.MALE,
        'country': 'US',
        'phone_number': '+48123456789',
        'date_of_birth': '2000-01-01',
    }


@pytest.fixture
def minimal_registration_data():
    """Minimal required registration data fixture."""
    return {
        'email': 'test@example.com',
        'first_name': 'John',
        'last_name': 'Doe',
        'password1': 'SecurePass123!',
        'password2': 'SecurePass123!',
        'phone_number': '+48123456789',
        'date_of_birth': '2000-01-01',
    }


@pytest.fixture
def existing_user():
    """Create an existing user for duplicate tests."""
    def _create_user(email='existing@example.com', phone_number='+48123456789'):
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
            phone_number='+48987654321',
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


# URL name fixtures for easy access
@pytest.fixture
def register_url():
    return reverse('userAuth:rest_register')


@pytest.fixture
def verify_email_url():
    return reverse('rest_verify_email')  # This comes from dj_rest_auth


@pytest.fixture
def login_url():
    return reverse('rest_login')  # This comes from dj_rest_auth