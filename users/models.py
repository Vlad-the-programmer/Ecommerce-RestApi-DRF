from django.conf import settings
from django.db import models
from django.core import validators
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser
from django_countries.fields import CountryField
from phonenumber_field.modelfields import PhoneNumberField

from common.models import CommonModel, AuthCommonModel
from users.managers import ProfileManager, CustomUserManager
from users.enums import UserRole, Gender


class UserRoles(CommonModel):
    """User Role model. It is used to assign a role to a user."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="user_roles")
    role = models.CharField(max_length=50, choices=UserRole.choices)
    description = models.TextField(max_length=2000, blank=True, null=True)

    def __str__(self):
        return f"{self.user} - {self.role}"

    class Meta:
        db_table = "user_roles"
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"
        ordering = ["-date_created"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=["user", "role", "is_deleted"]),
            models.Index(fields=["user", "is_deleted"]),
            models.Index(fields=["role", "is_deleted"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'role'],
                condition=models.Q(is_deleted=False),
                name='unique_user_role'
            )
        ]


# Core User model for authentication
class User(AuthCommonModel, AbstractUser):
    objects = CustomUserManager()

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
    role = models.ForeignKey('UserRoles', on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="users")

    def __str__(self):
        role_name = getattr(self.role, 'role', 'No Role') if self.role else "No Role"
        return f"{self.email} - {role_name}"

    class Meta:
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['email', 'role__role']
        indexes = AuthCommonModel.Meta.indexes + [
            # Critical authentication indexes
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['is_deleted', 'email']),
            models.Index(fields=['is_deleted', 'role']),
            models.Index(fields=['is_deleted', 'is_staff']),
            models.Index(fields=['is_deleted', 'is_superuser']),
            models.Index(fields=['date_joined', 'is_deleted']),
            models.Index(fields=['last_login', 'is_deleted']),
        ]


# Separate User model for user details
class Profile(CommonModel):
    objects = ProfileManager()

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='profile'
    )
    gender = models.CharField(
        _('Gender'),
        max_length=20,
        choices=Gender,
        default=Gender.NOT_SPECIFIED
    )
    country = CountryField(
        blank_label=_('(select country)'),
        null=True,
        blank=True
    )
    avatar = models.ImageField(
        verbose_name=_('A profile image'),
        upload_to='profiles/',
        blank=True,
        null=True
    )
    date_of_birth = models.DateField()
    phone_number = PhoneNumberField(unique=True)
    shipping_address = models.ForeignKey(
        "common.ShippingAddress",
        on_delete=models.SET_NULL,
        related_name="profiles",
        null=True,
        blank=True
    )
    billing_address = models.ForeignKey(
        "common.BillingAddress",
        on_delete=models.SET_NULL,
        related_name="profiles",
        null=True,
        blank=True
    )
    # Notifications and preferences
    newsletter_subscription = models.BooleanField(default=False)
    email_notifications = models.BooleanField(default=False)
    sms_notifications = models.BooleanField(default=False)
    preferred_currency = models.CharField(max_length=3, default='USD')
    preferred_language = models.CharField(max_length=10, default='en')

    # Loyalty/points system
    loyalty_points = models.IntegerField(default=0)
    membership_tier = models.CharField(max_length=20, default='standard')

    # Store preferences
    preferred_payment_method = models.CharField(max_length=50, blank=True)
    preferred_shipping_method = models.CharField(max_length=50, blank=True)

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

    def __str__(self):
        return f"{self.user.email}'s user"

    class Meta:
        db_table = 'profiles'
        verbose_name = _('Profile')
        verbose_name_plural = _('Profiles')
        ordering = ['user__email']
        indexes = CommonModel.Meta.indexes + [
            # Core relationship indexes (aligned with select_related)
            models.Index(fields=['user', 'is_deleted']),  # ProfileManager + user lookup
            models.Index(fields=['is_deleted', 'user']),  # Alternative order

            # Unique field indexes
            models.Index(fields=['phone_number', 'is_deleted']),  # Unique lookup on active

            # Common filtering combinations
            models.Index(fields=['is_deleted', 'country']),  # Regional analytics
            models.Index(fields=['is_deleted', 'date_of_birth']),  # Age-based queries

            # For notification preferences
            models.Index(fields=['is_deleted', 'newsletter_subscription']),

            # For addresses
            models.Index(fields=['shipping_address', 'is_deleted']),
            models.Index(fields=['billing_address', 'is_deleted']),
        ]