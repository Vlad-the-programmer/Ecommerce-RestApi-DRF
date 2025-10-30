from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from django_countries.serializer_fields import CountryField
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from common.validators import FileSizeValidator as CustomFileSizeValidator
from users.enums import Gender
from users.models import Profile


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Complete Profile Response Example',
            value={
                'uuid': '123e4567-e89b-12d3-a456-426614174000',
                'username': 'johndoe',
                'email': 'john@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'gender': 'male',
                'country': 'US',
                'avatar': 'https://example.com/media/profiles/avatar.jpg',
                'date_of_birth': '2000-01-01',
                'phone_number': '+48123456789',
                'is_active': True,
                'date_updated': '2023-01-01T12:00:00Z',
            },
            response_only=True,
            description='Complete user profile with nested user data'
        ),
        OpenApiExample(
            'Profile Update Example',
            value={
                'first_name': 'John',
                'last_name': 'Smith',
                'gender': 'female',
                'country': 'GB',
                'date_of_birth': '1995-05-15',
                'phone_number': '+48123456789'
            },
            request_only=True,
            description='Update profile and user information'
        )
    ]
)
class ProfileDetailsUpdateSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for user profile data with nested user information.
    """

    # User fields (nested)
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    username = serializers.CharField(source='user.username', read_only=True)

    # User fields that should be included in response
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)

    # Profile fields
    gender = serializers.ChoiceField(
        choices=Gender.choices,
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
        help_text=_('Profile picture for the user (JPEG, PNG, or GIF, max 5MB)'),
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'gif'],
                message=_('Only image files (JPEG, PNG, GIF) are allowed.')
            ),
            CustomFileSizeValidator(max_size=5 * 1024 * 1024, message=_('Maximum file size is 5MB.')),
        ]
    )
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Profile
        fields = [
            'uuid', 'email', 'first_name', 'last_name', 'username',
            'gender', 'country', 'avatar', 'date_of_birth', 'phone_number',
            'is_active', 'date_updated', 'date_joined', 'last_login'
        ]
        read_only_fields = [
            'uuid', 'email', 'username', 'is_active',
            'date_updated', 'date_joined', 'last_login'
        ]

    def to_internal_value(self, data):
        """
        Convert flat structure to nested structure for user data.
        """
        data = data.copy()

        # Map flat fields to nested user structure
        user_mapping = {
            'first_name': 'first_name',
            'last_name': 'last_name',
        }

        user_data = {}
        for flat_field, user_field in user_mapping.items():
            if flat_field in data:
                user_data[user_field] = data.pop(flat_field)

        if user_data:
            data['user'] = user_data

        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        """
        Update both profile and user data with validation.
        """
        user_data = validated_data.pop('user', {})

        # Update user data if provided
        if user_data:
            user = instance.user
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()

        # Handle avatar deletion
        if 'avatar' in validated_data and validated_data['avatar'] is None:
            if instance.avatar:
                instance.avatar.delete(save=False)

        # Update profile data
        instance = super().update(instance, validated_data)
        return instance

