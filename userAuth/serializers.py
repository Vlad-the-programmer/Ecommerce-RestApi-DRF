import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm

# Third-party
from django_countries.serializer_fields import CountryField
from drf_spectacular.types import OpenApiTypes
from phonenumber_field.serializerfields import PhoneNumberField

# DRF
from rest_framework import serializers

# Swagger
from drf_spectacular.utils import OpenApiExample, extend_schema_serializer, extend_schema_field

# dj-rest-auth
from dj_rest_auth.serializers import PasswordResetConfirmSerializer as DefaultPasswordResetConfirmSerializer
from dj_rest_auth.registration.serializers import RegisterSerializer as DefaultRegisterSerializer
from dj_rest_auth.serializers import LoginSerializer as DefaultUserLoginSerializer
from dj_rest_auth.serializers import PasswordChangeSerializer as DefaultPasswordChangeSerializer
from dj_rest_auth.serializers import JWTSerializer as DefaultJWTSerializer

# Simple JWT
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

# Local
from userAuth.validators import (
    validate_password_strength,
    PASSWORD_MIN_LENGTH,
    PASSWORD_MAX_LENGTH
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
        email = email.lower().strip()  # Normalize email

        # Check if email already exists in User model
        if User.all_objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")

        # You can also check EmailAddress model if you're using allauth
        from allauth.account.models import EmailAddress
        if EmailAddress.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")

        return email

    def validate_phone_number(self, phone_number):
        """Validate that phone number is not already in use and is valid."""

        # Check if phone number is already in use
        if Profile.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")

        # Return the string representation to avoid serialization issues
        return str(phone_number)

    def get_cleaned_data(self):
        """
        Return ALL the cleaned data in the format expected by allauth.
        """
        cleaned_data = super().get_cleaned_data()

        cleaned_data.update({
            'username': '',  # Empty since we're using email
            'first_name': self.validated_data.get('first_name', ''),
            'last_name': self.validated_data.get('last_name', ''),
        })

        return cleaned_data

    def custom_signup(self, request, user):
        """
        Custom signup processing - called by allauth after user creation.
        This is the recommended way to add custom logic in allauth.
        """
        # Create the profile with validated data
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

    def save(self, request):
        """
        Save the user and create their profile.
        Override to ensure proper user creation flow with allauth.
        """
        # Let allauth handle the user creation and email verification
        user = super().save(request)

        # Debug: Check what user was created
        logger.debug(f"User created: {user.id}, Email: '{user.email}', Active: {user.is_active}")

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

    @property
    def set_password_form_class(self):
        return SetPasswordForm


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'JWT Login Success Response',
            value={
                'access': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
                'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
                'user': {
                    'id': 1,
                    'email': 'john@example.com',
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'phone_number': '+48123456789',
                    'gender': 'male',
                    'country': 'US',
                    'date_of_birth': '2000-01-01',
                    'avatar': 'https://example.com/media/profiles/avatar.jpg'
                }
            },
            response_only=True,
            description='Successful login response with JWT tokens and user data'
        ),
        OpenApiExample(
            'JWT Login Without Profile',
            value={
                'access': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
                'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
                'user': {
                    'id': 2,
                    'email': 'jane@example.com',
                    'first_name': 'Jane',
                    'last_name': 'Smith',
                    'phone_number': None,
                    'gender': None,
                    'country': None,
                    'date_of_birth': None,
                    'avatar': None
                }
            },
            response_only=True,
            description='Login response when user has no profile data'
        ),
    ],
    component_name='JWTResponse'
)
class CustomJWTSerializer(DefaultJWTSerializer):
    """
    Custom JWT serializer that provides enhanced user data in login responses.
    """

    def _get_phone_number_string(self, profile):
        """Safely convert phone number to string."""
        if profile.phone_number:
            return str(profile.phone_number)
        return None

    def _get_avatar_url(self, profile):
        """Safely get avatar URL."""
        if profile.avatar:
            return profile.avatar.url
        return None

    def _get_country_name(self, profile):
        """Safely get country name."""
        if profile.country:
            return str(profile.country)
        return None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_user(self, obj):
        """
        Get enhanced user data including profile information.
        """
        user = obj['user']
        user_data = {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        }

        # Include profile data if available
        try:
            profile = user.profile
            user_data.update({
                'phone_number': self._get_phone_number_string(profile),
                'gender': profile.gender,
                'country': self._get_country_name(profile),
                'date_of_birth': profile.date_of_birth,
                'avatar': self._get_avatar_url(profile),
            })
        except Profile.DoesNotExist:
            # Set profile fields to None if profile doesn't exist
            user_data.update({
                'phone_number': None,
                'gender': None,
                'country': None,
                'date_of_birth': None,
                'avatar': None,
            })

        return user_data

    def validate(self, attrs):
        """
        Validate and return enhanced JWT response with user data.
        """
        data = super().validate(attrs)
        data['user'] = self.get_user({'user': self.user})
        return data


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Token Obtain Request',
            value={
                'email': 'john@example.com',
                'password': 'SecurePass123!'
            },
            request_only=True,
            description='Login credentials for token generation'
        ),
        OpenApiExample(
            'Token Obtain Response',
            value={
                'access': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
                'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
            },
            response_only=True,
            description='JWT tokens response with custom claims'
        ),
    ],
    component_name='TokenObtain'
)
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom token serializer that enhances JWT tokens with user claims.

    This serializer adds user-specific claims to the JWT tokens, allowing
    client applications to access basic user information without additional
    API calls. The claims are embedded directly in the token payload.

    Added Claims:
    - email: User's email address
    - first_name: User's first name
    - last_name: User's last name

    Security Note:
    - Claims are readable by anyone who has the token
    - Do not include sensitive information in claims
    - Tokens are signed but not encrypted by default
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['email'] = user.email
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name

        return token

