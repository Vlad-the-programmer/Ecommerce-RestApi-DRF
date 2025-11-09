import pytest
from unittest.mock import patch, MagicMock

from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model

from rest_framework import status

from users.serializers import EmailChangeRequestSerializer, EmailChangeConfirmSerializer
from users.utils import send_email_change_confirmation, send_email_change_success_notification


User = get_user_model()

pytestmark = pytest.mark.django_db


class TestEmailChangeRequestSerializer:
    """Test EmailChangeRequestSerializer validation and save methods."""

    def test_valid_new_email(self, verified_user, rf):
        """Test serializer with valid new email."""
        user, _, _, _ = verified_user
        request = rf.post('/')
        request.user = user

        data = {'new_email': 'newemail@example.com'}
        serializer = EmailChangeRequestSerializer(data=data, context={'request': request})

        assert serializer.is_valid()
        assert serializer.validated_data['new_email'] == 'newemail@example.com'

    def test_invalid_email_format(self, verified_user, rf):
        """Test serializer with invalid email format."""
        user, _, _, _ = verified_user
        request = rf.post('/')
        request.user = user

        data = {'new_email': 'invalid-email'}
        serializer = EmailChangeRequestSerializer(data=data, context={'request': request})

        assert not serializer.is_valid()
        assert 'new_email' in serializer.errors
        assert 'Enter a valid email address' in str(serializer.errors['new_email'])

    def test_same_as_current_email(self, verified_user, rf):
        """Test serializer when new email is same as current email."""
        user, _, _, _ = verified_user
        request = rf.post('/')
        request.user = user

        data = {'new_email': user.email}
        serializer = EmailChangeRequestSerializer(data=data, context={'request': request})

        assert not serializer.is_valid()
        assert 'new_email' in serializer.errors
        assert 'cannot be the same as current email' in str(serializer.errors['new_email'])

    def test_email_already_in_use(self, verified_user, existing_user, rf):
        """Test serializer when new email is already in use."""
        user, _, _, _ = verified_user
        existing_user_obj = existing_user(email='existing@example.com')
        request = rf.post('/')
        request.user = user

        data = {'new_email': 'existing@example.com'}
        serializer = EmailChangeRequestSerializer(data=data, context={'request': request})

        assert not serializer.is_valid()
        assert 'new_email' in serializer.errors
        assert 'already in use' in str(serializer.errors['new_email'])

    @patch('users.serializers.send_email_change_confirmation')
    def test_save_success(self, mock_send_email, verified_user, rf):
        """Test successful save method."""
        user, _, _, _ = verified_user
        request = rf.post('/')
        request.user = user
        mock_send_email.return_value = True

        data = {'new_email': 'newemail@example.com'}
        serializer = EmailChangeRequestSerializer(data=data, context={'request': request})
        serializer.is_valid()

        result = serializer.save()

        mock_send_email.assert_called_once_with(user, 'newemail@example.com', request)
        assert result == {'detail': 'Confirmation email has been sent to your new email address.'}

    @patch('users.serializers.send_email_change_confirmation')
    def test_save_failure(self, mock_send_email, verified_user, rf):
        """Test save method when email sending fails."""
        user, _, _, _ = verified_user
        request = rf.post('/')
        request.user = user
        mock_send_email.return_value = False

        data = {'new_email': 'newemail@example.com'}
        serializer = EmailChangeRequestSerializer(data=data, context={'request': request})
        serializer.is_valid()

        with pytest.raises(Exception) as exc_info:
            serializer.save()

        assert 'Failed to send confirmation email' in str(exc_info.value)
        mock_send_email.assert_called_once_with(user, 'newemail@example.com', request)


class TestEmailChangeConfirmSerializer:
    """Test EmailChangeConfirmSerializer validation and save methods."""

    def test_valid_confirmation_data(self, verified_user):
        """Test serializer with valid confirmation data."""
        user, _, _, _ = verified_user
        new_email = 'newemail@example.com'

        # Generate valid token data
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        email_b64 = urlsafe_base64_encode(force_bytes(new_email))
        token = default_token_generator.make_token(user)

        data = {
            'uidb64': uidb64,
            'email_b64': email_b64,
            'token': token
        }

        serializer = EmailChangeConfirmSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data['user'] == user
        assert serializer.validated_data['new_email'] == new_email
        assert serializer.validated_data['old_email'] == user.email

    def test_invalid_uidb64(self):
        """Test serializer with invalid uidb64."""
        data = {
            'uidb64': 'invalid_uid',
            'email_b64': urlsafe_base64_encode(force_bytes('test@example.com')),
            'token': 'invalid_token'
        }

        serializer = EmailChangeConfirmSerializer(data=data)
        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'Invalid confirmation link' in str(serializer.errors['non_field_errors'])

    def test_invalid_token(self, verified_user):
        """Test serializer with invalid token."""
        user, _, _, _ = verified_user
        new_email = 'newemail@example.com'

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        email_b64 = urlsafe_base64_encode(force_bytes(new_email))

        data = {
            'uidb64': uidb64,
            'email_b64': email_b64,
            'token': 'invalid_token'
        }

        serializer = EmailChangeConfirmSerializer(data=data)
        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'Invalid or expired confirmation link' in str(serializer.errors['non_field_errors'])

    def test_nonexistent_user(self):
        """Test serializer with non-existent user ID."""
        uidb64 = urlsafe_base64_encode(force_bytes(99999))  # Non-existent user ID
        email_b64 = urlsafe_base64_encode(force_bytes('test@example.com'))
        token = 'some_token'

        data = {
            'uidb64': uidb64,
            'email_b64': email_b64,
            'token': token
        }

        serializer = EmailChangeConfirmSerializer(data=data)
        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors

    def test_email_already_taken(self, verified_user, existing_user):
        """Test serializer when new email is already taken."""
        user, _, _, _ = verified_user
        existing_user_obj = existing_user(email='taken@example.com')
        new_email = 'taken@example.com'

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        email_b64 = urlsafe_base64_encode(force_bytes(new_email))
        token = default_token_generator.make_token(user)

        data = {
            'uidb64': uidb64,
            'email_b64': email_b64,
            'token': token
        }

        serializer = EmailChangeConfirmSerializer(data=data)
        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'already in use' in str(serializer.errors['non_field_errors'])

    @patch('users.serializers.send_email_change_success_notification')
    def test_save_success(self, mock_send_notification, verified_user, rf):
        """Test successful save method."""
        user, _, _, _ = verified_user
        old_email = user.email
        new_email = 'newemail@example.com'
        request = rf.post('/')

        # Generate valid token data
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        email_b64 = urlsafe_base64_encode(force_bytes(new_email))
        token = default_token_generator.make_token(user)

        data = {
            'uidb64': uidb64,
            'email_b64': email_b64,
            'token': token
        }

        serializer = EmailChangeConfirmSerializer(data=data, context={'request': request})
        serializer.is_valid()

        result = serializer.save()

        # Refresh user from database
        user.refresh_from_db()
        assert user.email == new_email
        mock_send_notification.assert_called_once_with(user, old_email, new_email, request)
        assert 'detail' in result
        assert 'user' in result
        assert 'successfully updated' in result['detail']

    def test_missing_required_fields(self):
        """Test serializer with missing required fields."""
        serializer = EmailChangeConfirmSerializer(data={})
        assert not serializer.is_valid()
        assert 'uidb64' in serializer.errors
        assert 'email_b64' in serializer.errors
        assert 'token' in serializer.errors


class TestEmailChangeViews:
    """Test email change API views."""

    def test_email_change_request_success(self, authenticated_client, email_change_request_url):
        """Test successful email change request."""
        with patch('users.serializers.send_email_change_confirmation') as mock_send_email:
            mock_send_email.return_value = True

            data = {'new_email': 'newemail@example.com'}
            response = authenticated_client.post(email_change_request_url, data)

            assert response.status_code == status.HTTP_200_OK
            assert 'Confirmation email has been sent' in response.data['detail']
            mock_send_email.assert_called_once()

    def test_email_change_request_invalid_data(self, authenticated_client, email_change_request_url):
        """Test email change request with invalid data."""
        data = {'new_email': 'invalid-email'}
        response = authenticated_client.post(email_change_request_url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'new_email' in response.data

    def test_email_change_request_unauthenticated(self, client, email_change_request_url):
        """Test email change request without authentication."""
        data = {'new_email': 'newemail@example.com'}
        response = client.post(email_change_request_url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_email_change_confirm_success(self, authenticated_client, verified_user, email_change_confirm_url):
        """Test successful email change confirmation."""
        user, _, _, _ = verified_user
        old_email = user.email
        new_email = 'newemail@example.com'

        with patch('users.serializers.send_email_change_success_notification') as mock_send_notification:
            # Generate valid token data
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            email_b64 = urlsafe_base64_encode(force_bytes(new_email))
            token = default_token_generator.make_token(user)

            url = email_change_confirm_url(uidb64, email_b64, token)
            response = authenticated_client.post(url)

            assert response.status_code == status.HTTP_200_OK
            assert 'successfully updated' in response.data['detail']

            # Verify email was changed
            user.refresh_from_db()
            assert user.email == new_email
            mock_send_notification.assert_called_once()

    def test_email_change_confirm_invalid_token(self, authenticated_client, verified_user, email_change_confirm_url):
        """Test email change confirmation with invalid token."""
        user, _, _, _ = verified_user
        new_email = 'newemail@example.com'

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        email_b64 = urlsafe_base64_encode(force_bytes(new_email))

        url = email_change_confirm_url(uidb64, email_b64, 'invalid_token')
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'non_field_errors' in response.data
        assert 'Invalid or expired confirmation link' in str(response.data['non_field_errors'])

    def test_email_change_confirm_email_taken(self, authenticated_client, verified_user, existing_user, email_change_confirm_url):
        """Test email change confirmation when email is already taken."""
        user, _, _, _ = verified_user
        existing_user_obj = existing_user(email='taken@example.com')
        new_email = 'taken@example.com'

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        email_b64 = urlsafe_base64_encode(force_bytes(new_email))
        token = default_token_generator.make_token(user)

        url = email_change_confirm_url(uidb64, email_b64, token)
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'non_field_errors' in response.data
        assert 'already in use' in str(response.data['non_field_errors'])

    def test_email_change_confirm_nonexistent_user(self, authenticated_client, email_change_confirm_url):
        """Test email change confirmation with non-existent user."""
        uidb64 = urlsafe_base64_encode(force_bytes(99999))
        email_b64 = urlsafe_base64_encode(force_bytes('test@example.com'))
        token = 'some_token'

        url = email_change_confirm_url(uidb64, email_b64, token)
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestEmailSendingUtils:
    """Test email sending utility functions."""

    @patch('users.utils.send_mail')
    @patch('users.utils.get_site_info')
    def test_send_email_change_confirmation_success(self, mock_get_site_info, mock_send_mail, verified_user, rf):
        """Test successful email change confirmation sending."""
        user, _, _, _ = verified_user
        request = rf.post('/')

        mock_get_site_info.return_value = ('example.com', 'Test Site')
        mock_send_mail.return_value = 1

        # Mock render_to_string at the module level to avoid template issues
        with patch('users.utils.render_to_string') as mock_render:
            mock_render.side_effect = [
                'Email Change Confirmation Subject',
                '<html>Email Change Confirmation HTML</html>',
                'Email Change Confirmation Plain Text'
            ]

            result = send_email_change_confirmation(user, 'newemail@example.com', request)

            assert result is True
            mock_send_mail.assert_called_once()

    @patch('users.utils.send_mail')
    @patch('users.utils.get_site_info')
    def test_send_email_change_confirmation_failure(self, mock_get_site_info, mock_send_mail, verified_user, rf):
        """Test email change confirmation sending failure."""
        user, _, _, _ = verified_user
        request = rf.post('/')

        mock_get_site_info.return_value = ('example.com', 'Test Site')
        mock_send_mail.side_effect = Exception('SMTP error')

        # Mock render_to_string to avoid template issues
        with patch('users.utils.render_to_string') as mock_render:
            mock_render.side_effect = [
                'Email Change Confirmation Subject',
                '<html>Email Change Confirmation HTML</html>',
                'Email Change Confirmation Plain Text'
            ]

            result = send_email_change_confirmation(user, 'newemail@example.com', request)

            assert result is False

    @patch('users.utils.send_mail')
    @patch('users.utils.render_to_string')
    @patch('users.utils.get_site_info')
    def test_send_email_change_success_notification(self, mock_get_site_info, mock_render, mock_send_mail,
                                                    verified_user, rf):
        """Test successful email change success notification."""
        user, _, _, _ = verified_user
        request = rf.post('/')

        mock_get_site_info.return_value = ('example.com', 'Test Site')
        mock_render.return_value = 'rendered_content'
        mock_send_mail.return_value = 1

        result = send_email_change_success_notification(user, 'old@example.com', 'new@example.com', request)

        assert result is True
        mock_send_mail.assert_called_once()

    def test_get_site_info_with_request(self, rf):
        """Test get_site_info function with request."""
        from users.utils import get_site_info

        request = rf.post('/')

        with patch('users.utils.Site.objects.get_current') as mock_get_current:
            mock_site = MagicMock()
            mock_site.domain = 'example.com'
            mock_site.name = 'Test Site'
            mock_get_current.return_value = mock_site

            domain, site_name = get_site_info(request)

            assert domain == 'example.com'
            assert site_name == 'Test Site'

    def test_get_site_info_fallback(self, rf):
        """Test get_site_info function fallback when Site is not available."""
        from django.conf import settings
        from users.utils import get_site_info

        request = rf.post('/')

        with patch('users.utils.Site.objects.get_current') as mock_get_current:
            mock_get_current.side_effect = Exception('Site not found')

            domain, site_name = get_site_info(request)

            # Check against the actual fallback values from your settings
            expected_domain = getattr(settings, 'SITE_DOMAIN', 'localhost:8000')
            expected_site_name = getattr(settings, 'SITE_NAME', 'Your Site')

            assert domain == expected_domain
            assert site_name == expected_site_name

    def test_get_site_info_with_settings_override(self, rf, settings):
        """Test get_site_info with custom settings."""
        from users.utils import get_site_info

        request = rf.post('/')
        settings.SITE_DOMAIN = 'custom-domain.com'
        settings.SITE_NAME = 'Custom Site Name'

        with patch('users.utils.Site.objects.get_current') as mock_get_current:
            mock_get_current.side_effect = Exception('Site not found')

            domain, site_name = get_site_info(request)

            assert domain == 'custom-domain.com'
            assert site_name == 'Custom Site Name'