import uuid

from django.conf import settings
from django.db import models
from django.core import validators
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser
from django_countries.fields import CountryField
from phonenumber_field.modelfields import PhoneNumberField

from .managers import UserManager
from common.models import CommonModel


class Gender(models.TextChoices):
    MALE = "male", _("Male")
    FEMALE = "female", _("Female")
    OTHER = "other", _("Other")
    NOT_SPECIFIED = "not_specified", _("Not Specified")


# Core User model for authentication
class User(AbstractUser):
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        primary_key=True,
        editable=False
    )
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
    def __str__(self):
        return self.email

    class Meta:
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['email']
        indexes = [
            models.Index(fields=['email', 'first_name', 'last_name', 'is_active'])
        ]


# Separate Profile model for user details
class Profile(CommonModel):
    id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        primary_key=True,
        editable=False
    )
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

    def __str__(self):
        return f"{self.user.email}'s user"

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

    class Meta:
        db_table = 'profiles'
        verbose_name = _('Profile')
        verbose_name_plural = _('Profiles')
        ordering = ['user__email']