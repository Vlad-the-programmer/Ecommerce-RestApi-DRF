from django.conf import settings
from django.db import models
from django.core import validators
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser
from django_countries.fields import CountryField
from phonenumber_field.modelfields import PhoneNumberField

from common.managers import NonDeletedObjectsManager
from common.models import CommonModel


class Gender(models.TextChoices):
    MALE = "male", _("Male")
    FEMALE = "female", _("Female")
    OTHER = "other", _("Other")
    NOT_SPECIFIED = "not_specified", _("Not Specified")


# Core User model for authentication
class User(CommonModel, AbstractUser):
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    email = models.EmailField(
        unique=True,
        validators=[validators.EmailValidator()]
    )
    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        blank=True,
        null=True,
        help_text=_(
            "Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
        ),
        validators=[AbstractUser.username_validator],
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )

    def delete(self, *args, **kwargs):
        """Soft delete user and their profile."""
        # Soft delete user using CommonModel's delete
        super().delete(*args, **kwargs)

        # Also soft delete the profile if it exists
        if hasattr(self, 'profile'):
            self.profile.delete()

    def __str__(self):
        return self.email

    class Meta(CommonModel.Meta):
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['email']
        indexes = CommonModel.Meta.indexes + [
            # User-specific single field indexes
            models.Index(fields=['email']),
            models.Index(fields=['username']),
            models.Index(fields=['first_name']),
            models.Index(fields=['last_name']),
            models.Index(fields=['date_joined']),
            models.Index(fields=['last_login']),

            # Composite indexes for common user queries
            models.Index(fields=['email', 'is_active']),
            models.Index(fields=['username', 'is_active']),
            models.Index(fields=['first_name', 'last_name']),
            models.Index(fields=['is_active', 'date_joined']),
            models.Index(fields=['is_staff', 'is_active']),
            models.Index(fields=['is_superuser', 'is_active']),

            # Search and filter combinations
            models.Index(fields=['last_login', 'is_active']),
            models.Index(fields=['date_joined', 'is_active', 'is_deleted']),

            # For admin and reporting queries
            models.Index(fields=['is_staff', 'is_superuser', 'is_active']),
        ]


# Separate User model for user details
class Profile(CommonModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    gender = models.CharField(
        _('Gender'),
        max_length=10,
        choices=Gender,
        default=Gender.NOT_SPECIFIED
    )
    country = CountryField(
        blank_label=_('(select country)'),
        default='',
        null=True,
        blank=True
    )
    avatar = models.ImageField(
        verbose_name=_('A profile image'),
        upload_to='profiles/',
        default='profiles/profile_default.jpg'
    )
    date_of_birth = models.DateField()
    phone_number = PhoneNumberField(unique=True, region='PL', blank=True)

    @property
    def get_full_name(self):
        return f"{self.user.first_name} {self.user.last_name}"

    @property
    def imageURL(self):
        try:
            url = self.avatar.url
        except:
            url = ''
        return url

    def delete(self, *args, **kwargs):
        """Soft delete both profile and user."""
        # Soft delete profile using CommonModel's delete
        super().delete(*args, **kwargs)

        # Also soft delete the user
        self.user.delete()

    def hard_delete(self, *args, **kwargs):
        """Actually delete the profile from database."""
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email}'s user"

    class Meta(CommonModel.Meta):
        db_table = 'profiles'
        verbose_name = _('Profile')
        verbose_name_plural = _('Profiles')
        ordering = ['user__email']
        indexes = CommonModel.Meta.indexes + [
            # Profile-specific single field indexes
            models.Index(fields=['user']),  # ForeignKey index
            models.Index(fields=['gender']),
            models.Index(fields=['country']),
            models.Index(fields=['date_of_birth']),
            models.Index(fields=['phone_number']),

            # Composite indexes for common profile queries
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['gender', 'country']),
            models.Index(fields=['date_of_birth', 'is_active']),
            models.Index(fields=['country', 'is_active']),

            # For user profile lookups
            models.Index(fields=['user', 'is_active', 'is_deleted']),
            models.Index(fields=['phone_number', 'is_active']),

            # For reporting and analytics
            models.Index(fields=['date_of_birth', 'gender', 'country']),
            models.Index(fields=['date_created', 'country', 'is_active']),
        ]