import pytest

from django.core import mail
from django.contrib.auth import get_user_model
from rest_framework import status

from userAuth.models import Profile, Gender

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestCustomRegisterView:
    """Test cases for CustomRegisterView."""

    def test_successful_registration(self, client, valid_registration_data, register_url):
        """Test successful user registration."""
        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert 'detail' in response.data
        assert response.data['detail'] == 'Verification e-mail sent.'

        # Check user was created
        user = User.objects.get(email='test@example.com')
        assert user.first_name == 'John'
        assert user.last_name == 'Doe'
        assert user.is_active is False  # Should be inactive until email verification
        assert user.username == 'test'  # Auto-generated from email

        # Check profile was created
        profile = Profile.objects.get(user=user)
        assert profile.gender == Gender.MALE
        assert profile.country == 'US'
        assert profile.phone_number == '+48123456789'
        assert str(profile.date_of_birth) == '2000-01-01'

    def test_registration_with_avatar(self, client, valid_registration_data, test_image, register_url):
        """Test registration with avatar file upload."""
        valid_registration_data['avatar'] = test_image

        response = client.post(register_url, valid_registration_data, format='multipart')

        assert response.status_code == status.HTTP_201_CREATED

        user = User.objects.get(email='test@example.com')
        profile = Profile.objects.get(user=user)
        assert profile.avatar.name.startswith('profiles/')

    def test_registration_missing_required_fields(self, client, register_url):
        """Test registration fails when required fields are missing."""
        invalid_data = {
            'email': 'test@example.com',
            # Missing first_name, last_name, phone_number, date_of_birth
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }

        response = client.post(register_url, invalid_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'first_name' in response.data
        assert 'last_name' in response.data
        assert 'phone_number' in response.data
        assert 'date_of_birth' in response.data

    def test_registration_duplicate_email(self, client, valid_registration_data, existing_user, register_url):
        """Test registration fails with duplicate email."""
        existing_user(email='existing@example.com')

        valid_registration_data['email'] = 'existing@example.com'
        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data

    def test_registration_duplicate_phone_number(self, client, valid_registration_data, existing_user, register_url):
        """Test registration fails with duplicate phone number."""
        existing_user(phone_number='+48123456789')

        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'phone_number' in response.data

    @pytest.mark.parametrize('weak_password', ['weak', '12345678', 'password', 'PASSWORD123'])
    def test_registration_weak_password(self, client, valid_registration_data, weak_password, register_url):
        """Test registration fails with weak password."""
        valid_registration_data['password1'] = weak_password
        valid_registration_data['password2'] = weak_password

        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password1' in response.data

    def test_registration_password_mismatch(self, client, valid_registration_data, register_url):
        """Test registration fails when passwords don't match."""
        valid_registration_data['password2'] = 'DifferentPass123!'

        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "The two password fields didn't match." in response.data

    @pytest.mark.parametrize('invalid_email', ['invalid-email', 'invalid@', '@example.com', 'invalid@.com'])
    def test_registration_invalid_email(self, client, valid_registration_data, invalid_email, register_url):
        """Test registration fails with invalid email format."""
        valid_registration_data['email'] = invalid_email

        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data

    @pytest.mark.parametrize('invalid_phone', ['invalid-phone', '123', '+48invalid', ''])
    def test_registration_invalid_phone_number(self, client, valid_registration_data, invalid_phone, register_url):
        """Test registration fails with invalid phone number."""
        valid_registration_data['phone_number'] = invalid_phone

        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'phone_number' in response.data

    def test_registration_optional_fields(self, client, minimal_registration_data, register_url):
        """Test registration with optional fields omitted."""
        response = client.post(register_url, minimal_registration_data, format='json')

        assert response.status_code == status.HTTP_201_CREATED

        user = User.objects.get(email='test@example.com')
        profile = Profile.objects.get(user=user)
        assert profile.gender == Gender.NOT_SPECIFIED  # Default value
        assert profile.country == ''  # Default value

    @pytest.mark.override_settings(ACCOUNT_EMAIL_VERIFICATION='none')
    def test_registration_without_email_verification(self, client, valid_registration_data, register_url):
        """Test registration when email verification is disabled."""
        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert 'key' in response.data  # Should return auth token

        user = User.objects.get(email='test@example.com')
        assert user.is_active is True  # Should be active immediately

    def test_email_sent_on_registration(self, client, valid_registration_data, register_url):
        """Test that verification email is sent after registration."""
        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert len(mail.outbox) == 1
        assert 'verify-email' in mail.outbox[0].body
        assert mail.outbox[0].to == ['test@example.com']

    def test_multipart_form_data_support(self, client, valid_registration_data, test_image, register_url):
        """Test that the view supports multipart form data for file uploads."""
        valid_registration_data['avatar'] = test_image

        response = client.post(register_url, valid_registration_data, format='multipart')

        assert response.status_code == status.HTTP_201_CREATED

    @pytest.mark.parametrize('email,expected_username', [
        ('test.user@example.com', 'test.user'),
        ('test.user+tag@example.com', 'test.user'),
        ('test@example.com', 'test'),
        ('upper.CASE@example.com', 'upper.case'),
    ])
    def test_username_auto_generation(self, client, valid_registration_data, email, expected_username, register_url):
        """Test that username is automatically generated from email."""
        valid_registration_data['email'] = email

        response = client.post(register_url, valid_registration_data, format='json')

        assert response.status_code == status.HTTP_201_CREATED

        user = User.objects.get(email=email)
        assert user.username == expected_username