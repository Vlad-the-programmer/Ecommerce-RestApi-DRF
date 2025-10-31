import logging

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from django_countries.serializer_fields import CountryField
from django.core.validators import FileExtensionValidator

from rest_framework import serializers

from common.serializers import BaseCustomModelSerializer
from common.validators import FileSizeValidator as CustomFileSizeValidator
from users.enums import Gender
from users.models import Profile


logger = logging.getLogger(__name__)
User = get_user_model()



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
    component_name='UserDetails',
    description="""
    Comprehensive serializer that combines User model data with related Profile information.
    Used by dj-rest-auth's UserDetailsView to provide complete user information in a single endpoint.

    Features:
    - Combines User and Profile model data
    - Handles profile creation if missing
    - Supports partial updates for both models
    - Includes proper validation for profile fields
    """
)
class UserDetailsSerializer(BaseCustomModelSerializer):
    """
    Serializer for user details that combines User and Profile data.
    Used by dj-rest-auth's UserDetailsView.
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
    phone_number = serializers.CharField(source='profile.phone_number', required=False, allow_blank=True,
                                         allow_null=True)
    is_active_profile = serializers.BooleanField(source='profile.is_active', read_only=True)
    date_updated = serializers.DateTimeField(source='profile.date_updated', read_only=True)

    class Meta:
        model = User
        fields = BaseCustomModelSerializer.Meta.fields + [
            'id', 'email', 'first_name', 'last_name', 'username',
            'uuid', 'gender', 'country', 'avatar', 'date_of_birth', 'phone_number',
            'is_active_profile', 'date_joined', 'last_login'
        ]
        read_only_fields = [
            'id', 'email', 'username', 'is_active_profile',
            'date_joined', 'last_login'
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

    def update(self, instance, validated_data):
        """
        Update both user and profile data.
        """
        profile_data = validated_data.pop('profile', {})

        # Update user fields
        instance = super().update(instance, validated_data)

        # Update or create profile
        if profile_data:
            profile, created = Profile.objects.get_or_create(user=instance)

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
    component_name='ProfileDetails',
    description="""
    Detailed serializer for Profile model with nested User information.
    Use this for profile-specific endpoints where you need full control over profile operations.

    Key Features:
    - Full profile data with nested user information
    - Image upload with validation
    - Support for avatar deletion
    - Comprehensive field validation
    """
)
class ProfileDetailsUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for Profile model only. Use for profile-specific endpoints.
    """
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    username = serializers.CharField(source='user.username', read_only=True)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)

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

    def update(self, instance, validated_data):
        """
        Update both profile and user data.
        """
        user_data = validated_data.pop('user', {})

        # Update user data
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
        return super().update(instance, validated_data)
