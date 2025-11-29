import logging
import random
import string
import pytest
import uuid

from io import BytesIO
from PIL import Image

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from django.utils import timezone
from django.db.models.signals import post_save
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command


# All auth
from allauth.account.models import EmailConfirmation, EmailAddress

from userAuth.signals import handle_user_creation
from users.enums import Gender, UserRole
from users.models import Profile, UserRoles


logger = logging.getLogger(__name__)

User = get_user_model()


def generate_valid_polish_phone_number():
    """Generate a valid Polish phone number for tests."""
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
        'phone_number': generate_valid_polish_phone_number(),
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
        'phone_number': generate_valid_polish_phone_number(),
        'date_of_birth': '2000-01-01',
    }


@pytest.fixture
def unverified_user(db, minimal_registration_data):
    """
    Create an unverified user with email confirmation.
    Returns:
            tuple: A tuple containing the user, profile, email address, and confirmation.
    """
    password = minimal_registration_data['password1']

    user = User.objects.create_user(
        email='unverified@example.com',
        first_name='Unverified',
        last_name='User',
        password=password,
        is_active=False
    )

    userRole = UserRole.objects.create(
        user=user,
        role=UserRole.CUSTOMER
    )

    user.role = userRole
    user.save(update_fields=['role', 'date_updated'])

    profile = Profile.objects.create(
        user=user,
        phone_number=generate_valid_polish_phone_number(),
        date_of_birth='1995-01-01',
        is_active=False
    )
    email_address = EmailAddress.objects.create(
        user=user,
        email=user.email,
        primary=True,
        verified=False
    )

    confirmation = EmailConfirmation.create(email_address)
    confirmation.sent = timezone.now()
    confirmation.save()

    logger.debug("Allauth generated key: '%s'", confirmation.key)

    return user, profile, email_address, confirmation


@pytest.fixture
def multiple_verified_users(minimal_registration_data):
    """Create multiple verified users for testing."""

    def _create_users(count=3):
        password = minimal_registration_data['password1']

        users = []
        for i in range(count):
            user = User.objects.create_user(
                email=f'user{i + 1}@example.com',
                first_name=f'User{i + 1}',
                last_name='Test',
                password='password123',
                is_active=True
            )

            userRole = UserRole.objects.create(
                user=user,
                role=UserRole.CUSTOMER
            )

            user.role = userRole
            user.save(update_fields=['role', 'date_updated'])

            Profile.objects.create(
                user=user,
                phone_number=generate_valid_polish_phone_number(),
                date_of_birth=f'199{0 + i}-01-01',
                gender=Gender.MALE if i % 2 == 0 else Gender.FEMALE,
                country='US',
                is_active=True
            )

            EmailAddress.objects.create(
                user=user,
                email=user.email,
                primary=True,
                verified=True
            )

            users.append(user)

        logger.debug("Created %d verified users", count)
        return users

    return _create_users


@pytest.fixture
def user_with_token(verified_user):
    """Create a verified user with an auth token."""

    def _create_user():
        user, profile, email_address, confirmation = verified_user

        from rest_framework.authtoken.models import Token
        token, created = Token.objects.get_or_create(user=user)

        logger.debug("Created user with token: %s", user.email)

        return user, profile, email_address, confirmation, token

    return _create_user


@pytest.fixture
def existing_user():
    """Create an existing user for duplicate tests."""

    def _create_user(email='existing@example.com', phone_number=None):
        # Disconnect the signal that sets is_active=False
        post_save.disconnect(receiver=handle_user_creation, sender=settings.AUTH_USER_MODEL)

        try:

            if phone_number is None:
                phone_number = generate_valid_polish_phone_number()

            user = User.objects.create_user(
                email=email,
                first_name='Existing',
                last_name='User',
                password='password123'
            )

            userRole = UserRole.objects.create(
                user=user,
                role=UserRole.CUSTOMER
            )

            user.role = userRole
            user.save(update_fields=['role', 'date_updated'])

            Profile.objects.create(
                user=user,
                phone_number=phone_number,
                date_of_birth='1990-01-01'
            )
            return user

        finally:
            # Reconnect the signal
            post_save.connect(handle_user_creation, sender=settings.AUTH_USER_MODEL)

    return _create_user


@pytest.fixture
def verified_user(db, minimal_registration_data):
    """
    Create a fully verified user with active profile.
    """

    # Temporarily disconnect the signal
    post_save.disconnect(receiver=handle_user_creation, sender=settings.AUTH_USER_MODEL)

    try:
        email = 'verified@example.com'
        password = minimal_registration_data['password1']

        user = User.objects.create_user(
            email=email,
            first_name='Verified',
            last_name='User',
            password=password,
            is_active=True
        )

        profile = Profile.objects.create(
            user=user,
            phone_number=generate_valid_polish_phone_number(),
            date_of_birth='1990-01-02',
            gender=Gender.MALE,
            country='US',
            is_active=True
        )

        email_address = EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=True
        )

        confirmation = EmailConfirmation.create(email_address)
        confirmation.sent = timezone.now()
        confirmation.save()

        logger.debug(f"Verified user created - User is_active: {user.is_active}")
        logger.debug(f"Profile is_active: {profile.is_active}")

        return user, profile, email_address, confirmation

    finally:
        # Reconnect the signal
        post_save.connect(handle_user_creation, sender=settings.AUTH_USER_MODEL)


@pytest.fixture
def admin_user(db):
    """Create an admin user for testing."""
    # Temporarily disconnect the signal
    post_save.disconnect(receiver=handle_user_creation, sender=settings.AUTH_USER_MODEL)

    try:
        user = User.objects.create_superuser(
            email='admin@gmail.com',
            password='adminpass123',
            first_name='Admin',
            last_name='User',
            is_active=True,
            is_staff=True,
            is_superuser=True
        )

        Profile.objects.create(
            user=user,
            phone_number=generate_valid_polish_phone_number(),
            date_of_birth='1990-01-01',
            gender=Gender.MALE,
            country='US',
            is_active=True
        )

        user.refresh_from_db()
        return user
    finally:
        # Reconnect the signal
        post_save.connect(handle_user_creation, sender=settings.AUTH_USER_MODEL)

@pytest.fixture
def admin_client(admin_user):
    """Create an authenticated admin client."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def user_with_different_data(minimal_registration_data):
    """Create a user with different profile data for testing updates."""

    def _create_user():
        password = minimal_registration_data['password1']

        user = User.objects.create_user(
            email='different@example.com',
            first_name='Different',
            last_name='Profile',
            password=password,
            is_active=True
        )

        profile = Profile.objects.create(
            user=user,
            phone_number='+48123456789',  # Specific phone for testing
            date_of_birth='1985-05-15',
            gender=Gender.OTHER,
            country='DE',  # Different country
            is_active=True
        )

        EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=True
        )

        logger.debug("Created user with different profile data: %s", user.email)
        return user, profile

    return _create_user


@pytest.fixture
def register_url():
    return reverse('userAuth:rest_register')


@pytest.fixture
def verify_email_url():
    return reverse('userAuth:rest_verify_email')

@pytest.fixture
def resend_verification_url():
    return reverse('userAuth:rest_resend_email')

@pytest.fixture
def password_reset_url():
    return reverse('userAuth:rest_password_reset')

@pytest.fixture
def password_reset_confirm_url():
    return reverse('userAuth:rest_password_reset_confirm')

@pytest.fixture
def password_change_url():
    return reverse('userAuth:rest_password_change')

@pytest.fixture
def logout_url():
    return reverse('userAuth:rest_logout')

@pytest.fixture
def token_verify_url():
    return reverse('userAuth:token_verify')


@pytest.fixture
def login_url():
    return reverse('userAuth:rest_login')


@pytest.fixture
def user_details_url():
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


@pytest.fixture
def email_change_request_url():
    from django.urls import reverse
    return reverse('users:email_change_request')


@pytest.fixture
def email_change_confirm_url():
    from django.urls import reverse
    def _url(uidb64, email_b64, token):
        return reverse('users:email_change_confirm', args=[uidb64, email_b64, token])

    return _url