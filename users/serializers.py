import logging

# Rest framework
from rest_framework import serializers

# Dj-rest-auth
from dj_rest_auth.serializers import UserDetailsSerializer

# OpenApi
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample

from django.contrib.auth import get_user_model
from django_countries.serializer_fields import CountryField
from django.core.validators import FileExtensionValidator

# Phone number
from phonenumber_field.serializerfields import PhoneNumberField

from common.validators import FileSizeValidator as CustomFileSizeValidator
from users.enums import Gender
from users.models import Profile


logger = logging.getLogger(__name__)
User = get_user_model()


class BaseUserProfileValidationSerializer(serializers.Serializer):
    """
    Base serializer with common validation logic for user and profile data.
    """

    def validate(self, attrs):
        """
        Validate the entire data set using common validation methods.
        """
        attrs = self._validate_username(attrs)
        return attrs

    def _validate_username(self, attrs):
        """
        Validate and handle username - common logic for both serializers.
        """
        # Get username based on serializer structure
        username, user_data, instance = self._get_username_context(attrs)

        if username is not None:  # Check for None, empty string is allowed for auto-generation
            if not username:
                # Auto-generate username from email if empty
                if instance:
                    user_instance = self._get_user_instance(instance)
                    if user_instance:
                        generated_username = User.objects.generate_username(user_instance.email)
                        self._set_username(attrs, generated_username, user_data)
                    else:
                        raise serializers.ValidationError({
                            'username': 'Username cannot be empty and no user instance available to generate one.'
                        })
                else:
                    raise serializers.ValidationError({
                        'username': 'Username cannot be empty.'
                    })
            else:
                # Check if username is already taken by another user
                if instance:
                    user_instance = self._get_user_instance(instance)
                    if user_instance and User.objects.filter(username=username).exclude(pk=user_instance.pk).exists():
                        raise serializers.ValidationError({
                            'username': 'A user with this username already exists.'
                        })

        return attrs

    # Abstract methods to be implemented by child classes
    def _get_username_context(self, attrs):
        """Extract username context - to be implemented by child classes."""
        raise NotImplementedError

    def _get_user_instance(self, instance):
        """Get user instance from serializer instance - to be implemented by child classes."""
        raise NotImplementedError

    def _set_username(self, attrs, username, user_data):
        """Set username in attrs - to be implemented by child classes."""
        raise NotImplementedError


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'User Details Response Example',
            value={
                'id': 1,
                'email': 'john@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'username': 'johndoe',
                'uuid': '123e4567-e89b-12d3-a456-426614174000',
                'gender': 'male',
                'country': 'US',
                'avatar': 'https://example.com/media/profiles/avatar.jpg',
                'date_of_birth': '2000-01-01',
                'phone_number': '+48123456789',
                'is_active': True,
                'is_active_profile': True,
                'date_updated': '2023-01-01T12:00:00Z',
                'date_joined': '2023-01-01T10:00:00Z',
                'last_login': '2023-01-01T15:30:00Z',
            },
            response_only=True,
            description='Complete user details with profile information'
        ),
        OpenApiExample(
            'User Update Request Example',
            value={
                'first_name': 'John',
                'last_name': 'Smith',
                'gender': 'female',
                'country': 'GB',
                'date_of_birth': '1995-05-15',
                'phone_number': '+48123456789'
            },
            request_only=True,
            description='Update user and profile information'
        ),
        OpenApiExample(
            'User Without Profile Example',
            value={
                'id': 2,
                'email': 'jane@example.com',
                'first_name': 'Jane',
                'last_name': 'Smith',
                'username': 'janesmith',
                'uuid': None,
                'gender': None,
                'country': None,
                'avatar': None,
                'date_of_birth': None,
                'phone_number': None,
                'is_active': True,
                'is_active_profile': None,
                'date_updated': None,
                'date_joined': '2023-01-01T10:00:00Z',
                'last_login': '2023-01-01T15:30:00Z',
            },
            response_only=True,
            description='User details when profile does not exist'
        ),
    ],
    component_name='UserDetails'
)
class CustomUserDetailsSerializer(BaseUserProfileValidationSerializer, UserDetailsSerializer):
    """
    Comprehensive serializer that combines User model data with related Profile information.
    """

    # Profile fields
    uuid = serializers.UUIDField(source='profile.uuid', read_only=True)
    gender = serializers.ChoiceField(
        source='profile.gender',
        choices=Gender.choices,
        allow_blank=True,
        allow_null=True,
        required=False
    )
    country = CountryField(source='profile.country', required=False)
    avatar = serializers.ImageField(
        source='profile.avatar',
        required=False,
        allow_null=True,
        use_url=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif']),
            CustomFileSizeValidator(max_size=5 * 1024 * 1024),
        ]
    )
    date_of_birth = serializers.DateField(source='profile.date_of_birth', required=False, allow_null=True)
    phone_number = PhoneNumberField(source='profile.phone_number', required=False)
    is_active_profile = serializers.BooleanField(source='profile.is_active', read_only=True)
    date_updated = serializers.DateTimeField(source='profile.date_updated', read_only=True)

    class Meta:
        model = User
        fields = [
            'pk', 'email', 'first_name', 'last_name', 'username',
            'uuid', 'gender', 'country', 'avatar', 'date_of_birth', 'phone_number',
            'is_active', 'is_active_profile', 'date_joined', 'last_login', 'date_updated'
        ]
        read_only_fields = [
            'pk', 'email', 'username', 'is_active_profile', 'date_joined', 'last_login', 'date_updated',
            'date_created',
        ]

    def to_representation(self, instance):
        """
        Ensure profile fields are included even if profile doesn't exist.
        """
        representation = super().to_representation(instance)

        # If profile doesn't exist, set profile fields to None
        if not hasattr(instance, 'profile'):
            profile_fields = ['uuid', 'gender', 'country', 'avatar', 'date_of_birth', 'phone_number',
                              'is_active_profile', 'date_updated']
            for field in profile_fields:
                representation[field] = None

        return representation

    def _get_username_context(self, attrs):
        """Extract username context for CustomUserDetailsSerializer."""
        username = attrs.get('username')
        user_data = None
        instance = getattr(self, 'instance', None)
        return username, user_data, instance

    def _get_user_instance(self, instance):
        """Get user instance for CustomUserDetailsSerializer."""
        return instance

    def _set_username(self, attrs, username, user_data):
        """Set username in attrs for CustomUserDetailsSerializer."""
        attrs['username'] = username

    def update(self, instance, validated_data):
        """
        Update both user and profile data.
        """
        profile_data = validated_data.pop('profile', {}) if 'profile' in validated_data else {}

        # Update user fields first
        user_fields = {k: v for k, v in validated_data.items() if k not in ['profile']}
        instance = super().update(instance, user_fields)

        # Update or create profile if there's profile data
        if profile_data:
            profile, created = Profile.objects.get_or_create(user=instance)

            # Handle country field - it might come as a string, convert to Country object
            if 'country' in profile_data and isinstance(profile_data['country'], str):
                from django_countries import countries
                # Validate country code
                if profile_data['country'] in countries:
                    # CountryField will handle the conversion internally
                    pass
                elif profile_data['country'] == '':
                    profile_data['country'] = None

            # Handle avatar deletion
            if 'avatar' in profile_data and profile_data['avatar'] is None:
                if profile.avatar:
                    profile.avatar.delete(save=False)

            # Update profile fields
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        return instance


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Complete Profile Response Example',
            value={
                'uuid': '123e4567-e89b-12d3-a456-426614174000',
                'email': 'john@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'username': 'johndoe',
                'gender': 'male',
                'country': 'US',
                'avatar': 'https://example.com/media/profiles/avatar.jpg',
                'date_of_birth': '2000-01-01',
                'phone_number': '+48123456789',
                'is_active': True,
                'date_updated': '2023-01-01T12:00:00Z',
                'date_joined': '2023-01-01T10:00:00Z',
                'last_login': '2023-01-01T15:30:00Z',
            },
            response_only=True,
            description='Complete profile information with user data'
        ),
        OpenApiExample(
            'Profile Update Request Example',
            value={
                'first_name': 'John',
                'last_name': 'Smith',
                'gender': 'female',
                'country': 'GB',
                'date_of_birth': '1995-05-15',
                'phone_number': '+48123456789',
                'avatar': None  # To delete avatar
            },
            request_only=True,
            description='Update profile and user information'
        ),
    ],
    component_name='ProfileDetails'
)
class ProfileDetailsUpdateSerializer(BaseUserProfileValidationSerializer, serializers.ModelSerializer):
    """
    Detailed serializer for Profile model with nested User information.
    """

    # User fields
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    username = serializers.CharField(source='user.username', required=False)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)

    # Profile fields
    gender = serializers.ChoiceField(
        choices=Gender.choices,
        allow_blank=True,
        allow_null=True,
        required=False
    )
    country = CountryField(required=False)
    avatar = serializers.ImageField(
        required=False,
        allow_null=True,
        use_url=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif']),
            CustomFileSizeValidator(max_size=5 * 1024 * 1024),
        ]
    )
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    phone_number = PhoneNumberField(required=False)

    class Meta:
        model = Profile
        fields = [
            'uuid', 'email', 'first_name', 'last_name', 'username',
            'gender', 'country', 'avatar', 'date_of_birth', 'phone_number',
            'is_active', 'date_updated', 'date_joined', 'last_login',
        ]
        read_only_fields = ['uuid', 'date_updated', 'date_created', 'email']

    def _get_username_context(self, attrs):
        """Extract username context for ProfileDetailsUpdateSerializer."""
        user_data = attrs.get('user', {})
        username = user_data.get('username') if user_data else None
        instance = getattr(self, 'instance', None)
        return username, user_data, instance

    def _get_user_instance(self, instance):
        """Get user instance for ProfileDetailsUpdateSerializer."""
        if instance and hasattr(instance, 'user'):
            return instance.user
        return None

    def _set_username(self, attrs, username, user_data):
        """Set username in attrs for ProfileDetailsUpdateSerializer."""
        if user_data is not None:
            if 'user' not in attrs:
                attrs['user'] = {}
            attrs['user']['username'] = username

    def update(self, instance, validated_data):
        """
        Update both profile and user data.
        """
        user_data = validated_data.pop('user', {}) if 'user' in validated_data else {}

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
        # Note: phone_number is automatically handled by PhoneNumberField
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance