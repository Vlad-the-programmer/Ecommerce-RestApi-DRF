import logging
import re
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

# Third-party
from django_countries.serializer_fields import CountryField

# DRF
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from dj_rest_auth.serializers import PasswordResetSerializer as DefaultPasswordResetSerializer
from dj_rest_auth.serializers import PasswordResetConfirmSerializer as DefaultPasswordResetConfirmSerializer
from dj_rest_auth.registration.serializers import RegisterSerializer as DefaultRegisterSerializer
from dj_rest_auth.serializers import LoginSerializer as DefaultUserLoginSerializer
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _

from common.validators import FileSizeValidator as CustomFileSizeValidator
# Local
from users.models import Gender
from .exceptions import NotOwner, UserAlreadyExists, WeakPasswordError

# Email handler
from base_utils.emails_handler import send_confirmation_email

# Constants
PASSWORD_MIN_LENGTH = 8
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_]+$')
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

Profile = get_user_model()

logger = logging.getLogger(__name__)


class PasswordField(serializers.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault('style', {})
        kwargs['style']['input_type'] = 'password'
        kwargs['write_only'] = True
        kwargs.setdefault('min_length', PASSWORD_MIN_LENGTH)
        super().__init__(**kwargs)
        self.validators.append(self._validate_password_strength)

    def _validate_password_strength(self, value):
        """Validate password strength."""
        if len(value) < PASSWORD_MIN_LENGTH:
            raise serializers.ValidationError(
                _(f'Password must be at least {PASSWORD_MIN_LENGTH} characters long.')
            )
        if not any(char.isdigit() for char in value):
            raise serializers.ValidationError(_('Password must contain at least one digit.'))
        if not any(char.isupper() for char in value):
            raise serializers.ValidationError(_('Password must contain at least one uppercase letter.'))
        if not any(char.islower() for char in value):
            raise serializers.ValidationError(_('Password must contain at least one lowercase letter.'))

class CustomLoginSerializer(DefaultUserLoginSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('username', None)  # exclude the username field

@extend_schema_serializer(
    exclude_fields=['is_staff', 'is_active'],
    examples=[
        OpenApiExample(
            'User Profile Example',
            value={
                'username': 'johndoe',
                'email': 'john@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'gender': 'M',
                'country': 'US',
                'featured_image': None,
                'date_joined': '2023-01-01T12:00:00Z',
                'last_login': '2023-01-01T12:00:00Z'
            },
            response_only=True
        )
    ]
)
class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile data.
    Used for retrieving and updating user information.
    """
    email = serializers.EmailField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=Profile.objects.all(),
                lookup='iexact',
                message=_('A user with this email already exists.')
            )
        ],
        error_messages={
            'invalid': _('Enter a valid email address.'),
            'blank': _('This field may not be blank.')
        }
    )
    username = serializers.CharField(
        max_length=100,
        required=False,
        validators=[
            UniqueValidator(
                queryset=Profile.objects.all(),
                lookup='iexact',
                message=_('A user with this username already exists.')
            )
        ],
        error_messages={
            'max_length': _('Username cannot be longer than 100 characters.'),
            'invalid': _('Username can only contain letters, numbers, and underscores.')
        }
    )
    gender = serializers.ChoiceField(
        choices=Gender,
        allow_blank=True,
        allow_null=True,
        required=False,
        error_messages={
            'invalid_choice': _('Please select a valid gender.')
        }
    )
    country = CountryField(
        required=False,
        help_text=_('ISO 3166-1 alpha-2 country code (e.g., US, GB, DE)')
    )
    featured_image = serializers.ImageField(

        required=False,
        allow_null=True,
        use_url=True,
        style={'input_type': 'file'},
        help_text=_('Profile picture for the user (JPEG, PNG, or GIF, max 5MB)'),
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'gif'],
                message=_('Only image files (JPEG, PNG, GIF) are allowed.')
            ),
            CustomFileSizeValidator(max_size=5 * 1024 * 1024, message=_('Maximum file size is 5MB.')),
        ]
    )
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Profile
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'gender',
            'country',
            'featured_image',
            'is_staff',
            'is_active',
            'date_joined',
            'last_login',
        ]
        read_only_fields = ['id', 'is_staff', 'is_active', 'date_joined', 'last_login']

    def validate_username(self, value):
        """Validate username format."""
        if not USERNAME_REGEX.match(value):
            raise serializers.ValidationError(
                _('Username can only contain letters, numbers, and underscores.')
            )
        return value.lower()

    def validate_email(self, value):
        """Validate email format."""
        if not EMAIL_REGEX.match(value):
            raise serializers.ValidationError(_('Enter a valid email address.'))
        return value.lower()

    def update(self, instance, validated_data):
        """Update user profile with validated data."""
        request = self.context.get('request')

        if not request or instance != request.user:
            raise NotOwner(_('You do not have permission to update this profile.'))

        # Don't allow updating email through this endpoint
        if 'email' in validated_data and validated_data['email'] != instance.email:
            raise serializers.ValidationError({
                'email': _('Email cannot be changed through this endpoint.')
            })

        # Process the image if provided
        if 'featured_image' in validated_data and validated_data['featured_image'] is None:
            # If None is passed, we want to clear the image
            instance.featured_image.delete(save=False)

        return super().update(instance, validated_data)

@extend_schema_serializer(
    exclude_fields=['is_staff', 'is_active'],
    examples=[
        OpenApiExample(
            'Registration Example',
            value={
                'email': 'user@example.com',
                'username': 'newuser',
                'first_name': 'John',
                'last_name': 'Doe',
                'password': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'gender': 'male',
                'country': 'US'
            },
            request_only=True
        )
    ]
)
class CustomRegisterSerializer(DefaultRegisterSerializer):
    """Custom registration serializer that extends the default dj-rest-auth register serializer."""
    username = None  # We don't want username in registration
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    gender = serializers.ChoiceField(choices=Gender, required=False)
    country = CountryField(required=False)

    def get_cleaned_data(self):
        return {
            'email': self.validated_data.get('email', ''),
            'first_name': self.validated_data.get('first_name', ''),
            'last_name': self.validated_data.get('last_name', ''),
            'password1': self.validated_data.get('password1', ''),
            'gender': self.validated_data.get('gender'),
            'country': self.validated_data.get('country'),
        }

class CustomPasswordResetSerializer(DefaultPasswordResetSerializer):
    """Custom password reset serializer."""

    @property
    def password_reset_form_class(self):
        return PasswordResetForm

class CustomPasswordResetConfirmSerializer(DefaultPasswordResetConfirmSerializer):
    """Custom password reset confirm serializer."""

    @property
    def set_password_form_class(self):
        return SetPasswordForm

class CustomPasswordChangeSerializer(serializers.Serializer):
    """Custom password change serializer."""
    old_password = serializers.CharField(required=True)
    new_password1 = serializers.CharField(required=True)
    new_password2 = serializers.CharField(required=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Your old password was entered incorrectly.')
        return value

    def validate(self, attrs):
        if attrs['new_password1'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password2": "The two password fields didn't match."})
        validate_password(attrs['new_password1'], self.context['request'].user)
        return attrs

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password1'])
        user.save()
        return user

