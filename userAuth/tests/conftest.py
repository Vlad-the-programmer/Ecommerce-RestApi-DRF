import logging

from django.utils import timezone

from allauth.account.models import EmailConfirmation

from users.models import Gender
from common.tests.conftest import *


logger = logging.getLogger(__name__)

User = get_user_model()



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
def existing_user(db):
    """Create an existing user for duplicate tests."""
    email = 'existing@example.com'
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


@pytest.fixture
def verified_user(db):
    """
    Create a fully verified user with active profile.
    Returns:
            tuple: A tuple containing the user, profile, email address, and confirmation.
    """
    email = 'verified@example.com'
    password = 'password123'

    # Create user
    user = User.objects.create_user(
        email=email,
        first_name='Verified',
        last_name='User',
        password=password,
        is_active=True
    )

    # Create profile
    profile = Profile.objects.create(
        user=user,
        phone_number=generate_valid_polish_phone_number(),
        date_of_birth='1990-01-01',
        gender=Gender.MALE,
        country='US',
        is_active=True
    )

    # Create verified email address
    email_address = EmailAddress.objects.create(
        user=user,
        email=user.email,
        primary=True,
        verified=True
    )

    # Create confirmation
    confirmation = EmailConfirmation.create(email_address)
    confirmation.sent = timezone.now()
    confirmation.save()

    logger.debug("Created verified user: %s", user.email)

    return user, profile, email_address, confirmation


@pytest.fixture
def unverified_user(db):
    """
    Create an unverified user with email confirmation.
    Returns:
            tuple: A tuple containing the user, profile, email address, and confirmation.
    """
    user = User.objects.create_user(
        email='unverified@example.com',
        first_name='Unverified',
        last_name='User',
        password='password123',
        is_active=False
    )
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
def authenticated_client(client, verified_user):
    """Create a client authenticated with a verified user."""
    user, _, _, _ = verified_user
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def multiple_verified_users():
    """Create multiple verified users for testing."""

    def _create_users(count=3):
        users = []
        for i in range(count):
            user = User.objects.create_user(
                email=f'user{i + 1}@example.com',
                first_name=f'User{i + 1}',
                last_name='Test',
                password='password123',
                is_active=True
            )

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

        # Create DRF auth token
        from rest_framework.authtoken.models import Token
        token, created = Token.objects.get_or_create(user=user)

        logger.debug("Created user with token: %s", user.email)

        return user, profile, email_address, confirmation, token

    return _create_user


@pytest.fixture
def admin_user():
    """Create an admin user for testing privileged operations."""

    def _create_user():
        user = User.objects.create_user(
            email='admin@example.com',
            first_name='Admin',
            last_name='User',
            password='adminpass123',
            is_active=True,
            is_staff=True,
            is_superuser=True
        )

        Profile.objects.create(
            user=user,
            phone_number=generate_valid_polish_phone_number(),
            date_of_birth='1980-01-01',
            gender=Gender.MALE,
            country='US',
            is_active=True
        )

        EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=True
        )

        logger.debug("Created admin user: %s", user.email)
        return user

    return _create_user


@pytest.fixture
def user_with_different_data():
    """Create a user with different profile data for testing updates."""

    def _create_user():
        user = User.objects.create_user(
            email='different@example.com',
            first_name='Different',
            last_name='Profile',
            password='password123',
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


# URL fixtures
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
