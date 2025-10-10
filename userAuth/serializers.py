import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model

# Third-party
from django_countries.serializer_fields import CountryField
from phonenumber_field.serializerfields import PhoneNumberField

# DRF
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from dj_rest_auth.serializers import PasswordResetConfirmSerializer as DefaultPasswordResetConfirmSerializer
from dj_rest_auth.registration.serializers import RegisterSerializer as DefaultRegisterSerializer
from dj_rest_auth.serializers import LoginSerializer as DefaultUserLoginSerializer
from dj_rest_auth.serializers import PasswordChangeSerializer as DefaultPasswordChangeSerializer
from django.contrib.auth.forms import SetPasswordForm
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _

from common.validators import FileSizeValidator as CustomFileSizeValidator
from userAuth.validators import (
    validate_password_strength, validate_user_already_exists_with_username,
    PASSWORD_MIN_LENGTH, USERNAME_REGEX, EMAIL_REGEX
)

# Local
from users.models import Gender, Profile


logger = logging.getLogger(__name__)
User = get_user_model()


# Custom fields
class PasswordField(serializers.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault('style', {})
        kwargs['style']['input_type'] = 'password'
        kwargs['write_only'] = True
        kwargs.setdefault('min_length', PASSWORD_MIN_LENGTH)
        kwargs.setdefault('max_length', PASSWORD_MIN_LENGTH)
        super().__init__(**kwargs)
        self.validators.append(validate_password_strength)


# Custom serializers
class CustomLoginSerializer(DefaultUserLoginSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('username', None)  # exclude the username field

# TODO: Write tests
@extend_schema_serializer(
    exclude_fields=['is_staff', 'is_active'],
    examples=[
        OpenApiExample(
            'User User Example',
            value={
                'username': 'johndoe',
                'email': 'john@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'gender': 'M',
                'country': 'US',
                'avatar': None,
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
    Used for retrieving user information.
    """
    email = serializers.EmailField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
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
                queryset=User.objects.all(),
                lookup='iexact',
                message=_('A user with this username already exists.')
            )
        ],
        error_messages={
            'max_length': _('Username cannot be longer than 100 characters.'),
            'invalid': _('Username can only contain letters, numbers, and underscores.')
        }
    )

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'is_staff',
            'is_active',
            'is_superuser',
            'date_joined',
            'last_login',
            'date_updated',
            'date_deleted'
        ]
        read_only_fields = ['id', 'is_staff', 'is_superuser', 'is_active',
                            'date_joined', 'last_login', 'date_updated', 'date_deleted']

    def validate_username(self, value):
        """Validate username format."""
        if value and not USERNAME_REGEX.match(value):
            raise serializers.ValidationError(
                _('Username can only contain letters, numbers, and underscores.')
            )
        return value.lower() if value else value

    def validate_email(self, value):
        """Validate email format."""
        if value and not EMAIL_REGEX.match(value):
            raise serializers.ValidationError(_('Enter a valid email address.'))
        return value.lower() if value else value


# TODO: Write tests
@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'User User Example',
            value={
                'username': 'johndoe',
                'email': 'john@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'gender': 'M',
                'country': 'US',
                'avatar': None,
                'date_of_birth': '2000-01-01',
                'phone_number': '+1234567890',
                'is_staff': False,
                'is_active': True,
                'is_superuser': False,
                'date_updated': '2023-01-01T12:00:00Z',
                'date_joined': '2023-01-01T12:00:00Z',
                'last_login': '2023-01-01T12:00:00Z'
            },
            response_only=True
        )
    ]
)
class ProfileDetailsSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile data.
    Used for retrieving user information.
    """
    username = serializers.CharField(
        source='user.username',
        required=False,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),  # Use User model, not User
                lookup='iexact',
                message=_('A user with this username already exists.')
            )
        ],
        error_messages={
            'max_length': _('Username cannot be longer than 100 characters.'),
            'invalid': _('Username can only contain letters, numbers, and underscores.')
        }
    )
    email = serializers.EmailField(
        source='user.email',
        required=False,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),  # Use User model, not User
                lookup='iexact',
                message=_('A user with this email already exists.')
            )
        ],
        error_messages={
            'invalid': _('Enter a valid email address.'),
            'blank': _('This field may not be blank.')
        }
    )
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)


    is_staff = serializers.BooleanField(source='user.is_staff', read_only=True)
    is_superuser = serializers.BooleanField(source='user.is_superuser', read_only=True)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)
    date_updated = serializers.DateTimeField(source='user.date_updated', read_only=True)

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
    avatar = serializers.ImageField(
        required=False,
        allow_null=True,
        use_url=True,
        style={'input_type': 'file'},
        help_text=_('User picture for the user (JPEG, PNG, or GIF, max 5MB)'),
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'gif'],
                message=_('Only image files (JPEG, PNG, GIF) are allowed.')
            ),
            CustomFileSizeValidator(max_size=5 * 1024 * 1024, message=_('Maximum file size is 5MB.')),
        ]
    )

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'is_staff',
            'is_superuser',
            'date_joined',
            'last_login',
            'date_updated',
            'gender',
            'country',
            'avatar',
            'is_active',
            'date_of_birth',
            'phone_number',
        ]
        read_only_fields = ['id', 'email']

    def to_internal_value(self, data):
        """Convert flat structure to nested structure for user data."""
        # Create a copy of the data
        data = data.copy()

        # Extract user-related fields and create nested structure
        user_data = {}
        user_fields = ['username', 'email', 'first_name', 'last_name']

        for field in user_fields:
            if field in data:
                user_data[field] = data.pop(field)

        # If we have any user data, add it as nested 'user' key
        if user_data:
            data['user'] = user_data

        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        """Update both profile and user data."""
        # Extract user data from validated_data (it will be there now thanks to to_internal_value)
        user_data = validated_data.pop('user', {})

        # Update User model fields if provided
        if user_data:
            user = instance.user
            for attr, value in user_data.items():
                if value is not None:
                    setattr(user, attr, value)
                    validate_user_already_exists_with_username(value)
            user.save()

        # Handle avatar deletion if None is passed
        if 'avatar' in validated_data and validated_data['avatar'] is None:
            if instance.avatar:
                instance.avatar.delete(save=False)

        # Update User model fields
        instance = super().update(instance, validated_data)

        return instance

@extend_schema_serializer(
    exclude_fields=['is_staff', 'is_superuser', 'is_active', 'date_updated',
                    'date_joined', 'last_login', 'date_deleted'],
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
                'country': 'US',
                'phone_number': '+1234567890',
                'date_of_birth': '2000-01-01',
                'avatar': 'path/to/avatar.jpg'
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
    phone_number = PhoneNumberField(required=True, region='PL', blank=True)
    date_of_birth = serializers.DateField(required=True)
    avatar = serializers.ImageField(required=False, allow_null=True, allow_empty_file=True)
    password1 = PasswordField()
    password2 = PasswordField()

    def validate_username(self, username):
        validate_user_already_exists_with_username(username)
        return super().validate_username()

    def get_cleaned_data(self):
        """Separate user data from profile data."""
        return {
            'user_data': {
                'email': self.validated_data.get('email', ''),
                'first_name': self.validated_data.get('first_name', ''),
                'last_name': self.validated_data.get('last_name', ''),
                'password1': self.validated_data.get('password1', ''),
            },
            'profile_data': {
                'gender': self.validated_data.get('gender'),
                'country': self.validated_data.get('country'),
                'phone_number': self.validated_data.get('phone_number'),
                'date_of_birth': self.validated_data.get('date_of_birth'),
                'avatar': self.validated_data.get('avatar'),
            }
        }

    def save(self, request=None):
        """Save user and profile data to appropriate models."""
        cleaned_data = self.get_cleaned_data()
        user_data = cleaned_data['user_data']
        profile_data = cleaned_data['profile_data']

        # Generate username from email
        user_data['username'] = user_data['email'].split('@')[0]

        # Create user using parent class
        user = super().save(request)

        # Update user with safe fields only
        User.objects.filter(pk=user.pk).update(
            first_name=user_data.get('first_name', ''),
            last_name=user_data.get('last_name', ''),
            is_active=False
        )

        # Refresh user instance
        user.refresh_from_db()

        # Create profile
        Profile.objects.create(
            user=user,
            **{k: v for k, v in profile_data.items() if v is not None}
        )

        return user

class CustomPasswordResetConfirmSerializer(DefaultPasswordResetConfirmSerializer):
    """Custom password reset confirm serializer."""
    new_password1 = PasswordField()
    new_password2 = PasswordField()

    @property
    def set_password_form_class(self):
        return SetPasswordForm

class CustomPasswordChangeSerializer(DefaultPasswordChangeSerializer):
    """Custom password change serializer."""
    old_password = PasswordField()
    new_password1 = PasswordField()


