import re

from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from rest_framework import serializers


User = get_user_model()

# Constants
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_]+$')
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def validate_password_strength(value: str, min_length: int=PASSWORD_MIN_LENGTH):
    """
    Comprehensive password strength validator for dj_rest_auth.
    """
    errors = []

    # Length check
    if len(value) < min_length:
        errors.append(_(f'Password must be at least {min_length} characters long.'))

    # Digit check
    if not any(char.isdigit() for char in value):
        errors.append(_('Password must contain at least one digit.'))

    # Uppercase check
    if not any(char.isupper() for char in value):
        errors.append(_('Password must contain at least one uppercase letter.'))

    # Lowercase check
    if not any(char.islower() for char in value):
        errors.append(_('Password must contain at least one lowercase letter.'))

    # Special character check (optional - uncomment if needed)
    # if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
    #     errors.append(_('Password must contain at least one special character.'))

    if errors:
        raise serializers.ValidationError(errors)

def validate_user_already_exists_with_username(username: str):
    if User.objects.filter(username=username).exists():
        raise serializers.ValidationError(_("User with this username already exists."))