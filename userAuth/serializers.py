import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.utils.translation import gettext_lazy as _


# Third-party
from django_countries.serializer_fields import CountryField
from phonenumber_field.serializerfields import PhoneNumberField

# DRF
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

# Swagger
from drf_spectacular.utils import OpenApiExample, extend_schema_serializer

# dj-rest-auth
from dj_rest_auth.serializers import PasswordResetConfirmSerializer as \
    DefaultPasswordResetConfirmSerializer, \
    UserDetailsSerializer

from dj_rest_auth.registration.serializers import RegisterSerializer as DefaultRegisterSerializer
from dj_rest_auth.serializers import LoginSerializer as DefaultUserLoginSerializer
from dj_rest_auth.serializers import PasswordChangeSerializer as DefaultPasswordChangeSerializer

from common.serializers import BaseCustomModelSerializer
# Local
from userAuth.validators import (
    validate_password_strength,
    PASSWORD_MIN_LENGTH, USERNAME_REGEX,
    EMAIL_REGEX, PASSWORD_MAX_LENGTH
)
from users.models import Gender, Profile


logger = logging.getLogger(__name__)
User = get_user_model()


# Custom fields
@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Valid Password Example',
            value='SecurePass123!',
            description='Password must contain uppercase, lowercase, digits and meet length requirements'
        )
    ]
)
class PasswordField(serializers.CharField):
    """
    Custom password field with security validation.

    Features:
    - Write-only field with password input type
    - Enforces minimum and maximum length
    - Validates password strength requirements
    - Includes digit, uppercase, and lowercase validation
    """

    def __init__(self, **kwargs):
        kwargs.setdefault('style', {})
        kwargs['style']['input_type'] = 'password'
        kwargs['write_only'] = True
        kwargs.setdefault('min_length', PASSWORD_MIN_LENGTH)
        kwargs.setdefault('max_length', PASSWORD_MAX_LENGTH)
        super().__init__(**kwargs)
        self.validators.append(validate_password_strength)


# Custom serializers
@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Login Request Example',
            value={
                'email': 'user@example.com',
                'password': 'SecurePass123!'
            },
            request_only=True,
            description='Email and password for authentication'
        ),
        OpenApiExample(
            'Login Response Example',
            value={
                'key': 'abc123def456ghi789',
                'user': {
                    'pk': 1,
                    'email': 'user@example.com',
                    'first_name': 'John',
                    'last_name': 'Doe'
                }
            },
            response_only=True,
            description='Authentication token and user data'
        )
    ]
)
class CustomLoginSerializer(DefaultUserLoginSerializer):
    """
    Custom login serializer for email-based authentication.

    Removes username field to enforce email-only login.
    Returns authentication key and user data upon successful login.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('username', None)  # exclude the username field


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'User Response Example',
            value={
                'uuid': '123e4567-e89b-12d3-a456-426614174000',
                'username': 'johndoe',
                'email': 'john@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'is_staff': False,
                'is_active': True,
                'is_superuser': False,
                'is_deleted': False,
                'date_updated': '2023-01-01T12:00:00Z',
                'date_deleted': '2023-01-01T12:00:00Z',
                'date_joined': '2023-01-01T12:00:00Z',
                'last_login': '2023-01-01T12:00:00Z'
            },
            response_only=True,
            description='Complete user information',
        ),
    ]
)
class UserSerializer(BaseCustomModelSerializer, UserDetailsSerializer):
    """
    Serializer for user profile data.

    Used for:
    - Retrieving complete user information
    - Updating user profile details
    - Email and username validation with uniqueness checks

    All sensitive fields are read-only for security.
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

    class Meta(BaseCustomModelSerializer.Meta, UserDetailsSerializer.Meta):
        fields = (BaseCustomModelSerializer.Meta.fields
                  + list(UserDetailsSerializer.Meta.fields)
                  + ['is_staff', 'is_superuser', 'date_joined', 'last_login'])
        read_only_fields = (BaseCustomModelSerializer.Meta.read_only_fields
                            + list(UserDetailsSerializer.Meta.read_only_fields)
                            + ['is_staff', 'is_superuser', 'date_joined', 'last_login'])

    def validate_username(self, username: str):
        """Validate username format against allowed character pattern."""
        super().validate_username(username)
        if username and not USERNAME_REGEX.match(username):
            raise serializers.ValidationError(
                _('Username can only contain letters, numbers, and underscores.')
            )
        return username.lower() if username else username

    def validate_email(self, value):
        """Validate email format and normalize to lowercase."""
        if value and not EMAIL_REGEX.match(value):
            raise serializers.ValidationError(_('Enter a valid email address.'))
        return value.lower() if value else value


@extend_schema_serializer(
    exclude_fields=['is_staff', 'is_superuser', 'is_active', 'date_updated', 'is_deleted',
                    'date_joined', 'last_login', 'date_deleted'],
    examples=[
        OpenApiExample(
            'Successful Registration Request',
            value={
                'email': 'user@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'password1': 'SecurePass123!',
                'password2': 'SecurePass123!',
                'gender': 'male',
                'country': 'US',
                'phone_number': '+48123456789',
                'date_of_birth': '2000-01-01',
                'avatar': 'path/to/avatar.jpg'
            },
            request_only=True,
            description='Complete registration data with profile information'
        ),
        OpenApiExample(
            'Registration Response (Email Verification Enabled)',
            value={
                "detail": "Verification e-mail sent."
            },
            response_only=True,
            description='Success response when email verification is required - user must verify email before logging in'
        ),
        OpenApiExample(
            'Registration Response (Email Verification Disabled)',
            value={
                "key": "abc123def456ghi789"
            },
            response_only=True,
            description='Success response when email verification is disabled - returns authentication token for immediate login'
        )
    ]
)
class CustomRegisterSerializer(DefaultRegisterSerializer):
    """
    Custom registration serializer with extended profile fields.

    Creates both User and Profile models during registration.
    Features:
    - Email-based registration (username auto-generated)
    - Extended profile information collection
    - Phone number validation for Polish region
    - Profile image upload support
    - Automatic username generation from email
    - User set as inactive until email verification
    """
    username = None  # We don't want username in registration
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    gender = serializers.ChoiceField(choices=Gender, required=False, allow_blank=True,
                                     default=Gender.NOT_SPECIFIED)
    country = CountryField(required=False, allow_blank=True)
    phone_number = PhoneNumberField(required=True)
    date_of_birth = serializers.DateField(required=True)
    avatar = serializers.ImageField(required=False, allow_null=True, allow_empty_file=True)
    password1 = PasswordField()
    password2 = PasswordField()

    def validate_email(self, email):
        """Validate that email is not already in use."""
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_phone_number(self, phone_number):
        """Validate that phone number is not already in use."""
        if Profile.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return phone_number

    def get_cleaned_data(self):
        """
        Return ALL the cleaned data in the format expected by allauth.
        """
        return {
            'username': '',  # Empty since we're using email
            'password1': self.validated_data.get('password1', ''),
            'email': self.validated_data.get('email', ''),
            'first_name': self.validated_data.get('first_name', ''),
            'last_name': self.validated_data.get('last_name', ''),
        }

    def save(self, request):
        """
        Save the user and create their profile.
        """
        # Let allauth create the user first
        user = super().save(request)

        # Debug: Check what user was created
        print(f"🔧 User created: {user.id}, Email: '{user.email}'")

        # Create the profile
        profile_data = {
            'gender': self.validated_data.get('gender'),
            'country': self.validated_data.get('country'),
            'phone_number': self.validated_data.get('phone_number'),
            'date_of_birth': self.validated_data.get('date_of_birth'),
            'avatar': self.validated_data.get('avatar'),
        }

        # Remove None values
        profile_data = {k: v for k, v in profile_data.items() if v is not None}

        Profile.objects.create(user=user, **profile_data)

        return user


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Password Reset Confirm Request',
            value={
                'new_password1': 'NewSecurePass123!',
                'new_password2': 'NewSecurePass123!',
                'uid': 'MQ',  # base64 encoded user ID
                'token': 'abc123-def456-ghi789'
            },
            request_only=True,
            description='New password with reset confirmation tokens'
        ),
        OpenApiExample(
            'Password Reset Confirm Response',
            value={
                'detail': 'Password has been reset with the new password.'
            },
            response_only=True,
            description='Successful password reset confirmation'
        ),
        OpenApiExample(
            'Password Reset Error - Invalid Token',
            value={
                'token': ['Invalid value']
            },
            response_only=True,
            description='Error when reset token is invalid or expired'
        ),
        OpenApiExample(
            'Password Reset Error - Password Mismatch',
            value={
                'new_password2': ["The two password fields didn't match."]
            },
            response_only=True,
            description='Error when new passwords do not match'
        )
    ]
)
class CustomPasswordResetConfirmSerializer(DefaultPasswordResetConfirmSerializer):
    """
    Custom password reset confirmation serializer.

    Handles password reset flow with security validation:
    - Validates password strength requirements
    - Ensures password confirmation matches
    - Uses secure password reset tokens
    """
    new_password1 = PasswordField()
    new_password2 = PasswordField()

    def validate(self, attrs):
        """
        Add custom validation for password matching.
        """
        if attrs['new_password1'] != attrs['new_password2']:
            raise serializers.ValidationError({
                'new_password2': _("The two password fields didn't match.")
            })
        return super().validate(attrs)

    @property
    def set_password_form_class(self):
        return SetPasswordForm


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Password Change Request',
            value={
                'old_password': 'OldSecurePass123!',
                'new_password1': 'NewSecurePass123!',
                'new_password2': 'NewSecurePass123!'
            },
            request_only=True,
            description='Current password and new password with confirmation'
        ),
        OpenApiExample(
            'Password Change Response',
            value={
                'detail': 'New password has been saved.'
            },
            response_only=True,
            description='Successful password change confirmation'
        ),
        OpenApiExample(
            'Password Change Error - Wrong Old Password',
            value={
                'old_password': ['Invalid old password.']
            },
            response_only=True,
            description='Error when old password is incorrect'
        )
    ]
)
class CustomPasswordChangeSerializer(DefaultPasswordChangeSerializer):
    """
    Custom password change serializer for authenticated users.

    Allows users to change their password while:
    - Verifying current password
    - Validating new password strength
    - Ensuring new password confirmation matches
    - Maintaining security standards
    """
    old_password = PasswordField()
    new_password1 = PasswordField()
    new_password2 = PasswordField()

    def validate_old_password(self, value):
        """
        Validate that the old password is correct.
        """
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_('Invalid old password.'))
        return value

    def validate(self, attrs):
        """
        Validate that new passwords match.
        """
        if attrs['new_password1'] != attrs['new_password2']:
            raise serializers.ValidationError({
                'new_password2': _("The two password fields didn't match.")
            })
        return attrs


