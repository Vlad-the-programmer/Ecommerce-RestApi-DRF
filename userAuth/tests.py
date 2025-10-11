import os
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from allauth.account.models import EmailConfirmation, EmailAddress
from unittest.mock import patch, MagicMock

from users.models import Profile, Gender
from userAuth.views import CustomRegisterView, VerifyEmailView

User = get_user_model()


def create_test_image():
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


class CustomRegisterViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('rest_register')
        self.valid_data = {
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

    def test_successful_registration(self):
        """Test successful user registration."""
        response = self.client.post(self.register_url, self.valid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('detail', response.data)
        self.assertEqual(response.data['detail'], 'Verification e-mail sent.')

        # Check user was created
        user = User.objects.get(email='test@example.com')
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertFalse(user.is_active)  # Should be inactive until email verification
        self.assertEqual(user.username, 'test')  # Auto-generated from email

        # Check profile was created
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.gender, Gender.MALE)
        self.assertEqual(profile.country, 'US')
        self.assertEqual(profile.phone_number, '+48123456789')
        self.assertEqual(str(profile.date_of_birth), '2000-01-01')

    def test_registration_with_avatar(self):
        """Test registration with avatar file upload."""
        data = self.valid_data.copy()
        data['avatar'] = create_test_image()

        response = self.client.post(self.register_url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email='test@example.com')
        profile = Profile.objects.get(user=user)
        self.assertTrue(profile.avatar.name.startswith('profiles/'))

    def test_registration_missing_required_fields(self):
        """Test registration fails when required fields are missing."""
        invalid_data = {
            'email': 'test@example.com',
            # Missing first_name, last_name, phone_number, date_of_birth
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }

        response = self.client.post(self.register_url, invalid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('first_name', response.data)
        self.assertIn('last_name', response.data)
        self.assertIn('phone_number', response.data)
        self.assertIn('date_of_birth', response.data)

    def test_registration_duplicate_email(self):
        """Test registration fails with duplicate email."""
        # Create existing user
        User.objects.create_user(
            email='existing@example.com',
            first_name='Existing',
            last_name='User',
            password='password123'
        )

        data = self.valid_data.copy()
        data['email'] = 'existing@example.com'

        response = self.client.post(self.register_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_registration_duplicate_phone_number(self):
        """Test registration fails with duplicate phone number."""
        # Create existing user with phone number
        user = User.objects.create_user(
            email='existing@example.com',
            first_name='Existing',
            last_name='User',
            password='password123'
        )
        Profile.objects.create(
            user=user,
            phone_number='+48123456789',
            date_of_birth='1990-01-01'
        )

        response = self.client.post(self.register_url, self.valid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', response.data)

    def test_registration_weak_password(self):
        """Test registration fails with weak password."""
        data = self.valid_data.copy()
        data['password1'] = 'weak'
        data['password2'] = 'weak'

        response = self.client.post(self.register_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password1', response.data)

    def test_registration_password_mismatch(self):
        """Test registration fails when passwords don't match."""
        data = self.valid_data.copy()
        data['password2'] = 'DifferentPass123!'

        response = self.client.post(self.register_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password2', response.data)

    def test_registration_invalid_email(self):
        """Test registration fails with invalid email format."""
        data = self.valid_data.copy()
        data['email'] = 'invalid-email'

        response = self.client.post(self.register_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_registration_invalid_phone_number(self):
        """Test registration fails with invalid phone number."""
        data = self.valid_data.copy()
        data['phone_number'] = 'invalid-phone'

        response = self.client.post(self.register_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone_number', response.data)

    def test_registration_optional_fields(self):
        """Test registration with optional fields omitted."""
        data = {
            'email': 'test@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'phone_number': '+48123456789',
            'date_of_birth': '2000-01-01',
            # gender and country are optional
        }

        response = self.client.post(self.register_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email='test@example.com')
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.gender, Gender.NOT_SPECIFIED)  # Default value
        self.assertEqual(profile.country, '')  # Default value

    @override_settings(ACCOUNT_EMAIL_VERIFICATION='none')
    def test_registration_without_email_verification(self):
        """Test registration when email verification is disabled."""
        data = self.valid_data.copy()

        response = self.client.post(self.register_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('key', response.data)  # Should return auth token

        user = User.objects.get(email='test@example.com')
        self.assertTrue(user.is_active)  # Should be active immediately

    def test_email_sent_on_registration(self):
        """Test that verification email is sent after registration."""
        response = self.client.post(self.register_url, self.valid_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('verify-email', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['test@example.com'])

    def test_multipart_form_data_support(self):
        """Test that the view supports multipart form data for file uploads."""
        data = self.valid_data.copy()
        data['avatar'] = create_test_image()

        response = self.client.post(self.register_url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_username_auto_generation(self):
        """Test that username is automatically generated from email."""
        data = self.valid_data.copy()
        data['email'] = 'test.user+tag@example.com'

        response = self.client.post(self.register_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email='test.user+tag@example.com')
        self.assertEqual(user.username, 'test.user')  # Should extract local part


class VerifyEmailViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.verify_email_url = reverse('rest_verify_email')

        # Create a user and email confirmation
        self.user = User.objects.create_user(
            email='test@example.com',
            first_name='John',
            last_name='Doe',
            password='password123',
            is_active=False  # Initially inactive
        )
        self.profile = Profile.objects.create(
            user=self.user,
            phone_number='+48123456789',
            date_of_birth='2000-01-01',
            is_active=False  # Initially inactive
        )

        # Create email address and confirmation
        self.email_address = EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=False
        )
        self.confirmation = EmailConfirmation.objects.create(
            email_address=self.email_address
        )

    def test_successful_email_verification(self):
        """Test successful email verification."""
        data = {'key': self.confirmation.key}

        response = self.client.post(self.verify_email_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['detail'], 'Email successfully verified. You can now log in.')

        # Refresh user and profile from database
        self.user.refresh_from_db()
        self.profile.refresh_from_db()

        # Check that user and profile are now active
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.profile.is_active)

        # Check that email is verified
        self.email_address.refresh_from_db()
        self.assertTrue(self.email_address.verified)

    def test_email_verification_invalid_key(self):
        """Test email verification with invalid key."""
        data = {'key': 'invalid-key'}

        response = self.client.post(self.verify_email_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('detail', response.data)

    def test_email_verification_missing_key(self):
        """Test email verification with missing key."""
        response = self.client.post(self.verify_email_url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('key', response.data)

    @patch('userAuth.views.EmailConfirmationHMAC')
    def test_email_verification_exception_handling(self, mock_confirmation):
        """Test exception handling during email verification."""
        mock_confirmation.objects.get.side_effect = Exception('Test error')

        data = {'key': 'any-key'}

        response = self.client.post(self.verify_email_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn('detail', response.data)
        self.assertIn('An error occurred', response.data['detail'])

    def test_email_verification_already_verified(self):
        """Test email verification for already verified email."""
        # Mark email as already verified
        self.email_address.verified = True
        self.email_address.save()

        data = {'key': self.confirmation.key}

        response = self.client.post(self.verify_email_url, data, format='json')

        # Should still return success
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_email_verification_activates_correct_user(self):
        """Test that verification activates the correct user."""
        # Create another user
        other_user = User.objects.create_user(
            email='other@example.com',
            first_name='Other',
            last_name='User',
            password='password123',
            is_active=False
        )
        other_profile = Profile.objects.create(
            user=other_user,
            phone_number='+48987654321',
            date_of_birth='1995-01-01',
            is_active=False
        )

        data = {'key': self.confirmation.key}
        response = self.client.post(self.verify_email_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify correct user is activated
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        other_user.refresh_from_db()
        other_profile.refresh_from_db()

        self.assertTrue(self.user.is_active)
        self.assertTrue(self.profile.is_active)
        self.assertFalse(other_user.is_active)  # Other user should remain inactive
        self.assertFalse(other_profile.is_active)


class IntegrationTests(APITestCase):
    """Integration tests for the complete registration and verification flow."""

    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('rest_register')
        self.verify_email_url = reverse('rest_verify_email')
        self.login_url = reverse('rest_login')

        self.registration_data = {
            'email': 'test@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'phone_number': '+48123456789',
            'date_of_birth': '2000-01-01',
        }

    def test_complete_registration_verification_login_flow(self):
        """Test complete flow: registration -> email verification -> login."""
        # Step 1: Register
        response = self.client.post(self.register_url, self.registration_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Step 2: Extract verification key from email
        self.assertEqual(len(mail.outbox), 1)
        email_body = mail.outbox[0].body
        # In a real test, you'd parse the verification key from the email body
        # For this test, we'll get it from the database
        user = User.objects.get(email='test@example.com')
        email_address = EmailAddress.objects.get(email=user.email)
        confirmation = EmailConfirmation.objects.get(email_address=email_address)

        # Step 3: Verify email
        verify_data = {'key': confirmation.key}
        response = self.client.post(self.verify_email_url, verify_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Step 4: Login with verified account
        login_data = {
            'email': 'test@example.com',
            'password': 'SecurePass123!'
        }
        response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('key', response.data)  # Should return auth token

    def test_login_before_verification_fails(self):
        """Test that login fails before email verification."""
        # Register but don't verify
        response = self.client.post(self.register_url, self.registration_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Try to login
        login_data = {
            'email': 'test@example.com',
            'password': 'SecurePass123!'
        }
        response = self.client.post(self.login_url, login_data, format='json')

        # Should fail because account is not active
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# Clean up test files
@override_settings(MEDIA_ROOT='/tmp/test_media/')
class TestCleanup(TestCase):
    def test_cleanup_test_files(self):
        """Ensure test files are cleaned up."""
        # This is just a placeholder to indicate where file cleanup would happen
        # In a real project, you might want to implement proper cleanup
        pass