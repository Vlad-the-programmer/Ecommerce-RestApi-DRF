from django.conf import settings
from django.db import models
from django.core import validators
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser
from django_countries.fields import CountryField
from phonenumber_field.modelfields import PhoneNumberField

from common.models import CommonModel, AuthCommonModel
from userAuth.managers import ProfileManager, CustomUserManager


class Gender(models.TextChoices):
    MALE = "male", _("Male")
    FEMALE = "female", _("Female")
    OTHER = "other", _("Other")
    NOT_SPECIFIED = "not_specified", _("Not Specified")


class ShippingAddress(CommonModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Address line approach (common for e-commerce)
    address_line_1 = models.CharField(max_length=255, help_text=_("Street address, P.O. box, company name"))
    address_line_2 = models.CharField(max_length=255, blank=True, null=True,
                                      help_text=_("Apartment, suite, unit, building, floor, etc."))
    # Optional detailed breakdown
    house_number = models.CharField(max_length=20, blank=True, null=True)
    street = models.CharField(max_length=100, blank=True, null=True)
    apartment_number = models.CharField(max_length=50, blank=True, null=True)
    zip_code = models.CharField(max_length=15, null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    state = models.CharField(max_length=50, null=True, blank=True,
                             help_text=_("State/Province/Region (e.g., Massachusetts, Ontario, Bavaria)"))
    country = CountryField(null=True, blank=True)
    is_default = models.BooleanField(default=False, help_text=_("Set as default shipping address"))

    def __str__(self):
        parts = []
        if self.address_line_1:
            parts.append(self.address_line_1)
        if self.address_line_2:
            parts.append(self.address_line_2)
        parts.extend([self.city, self.state, self.zip_code, str(self.country)])
        return ', '.join(parts)

    class Meta(CommonModel.Meta):
        db_table = "shipping_addresses"
        verbose_name = "Shipping Address"
        verbose_name_plural = "Shipping Addresses"
        ordering = ["-is_default", "-date_created"]  # Default addresses first, then newest
        indexes = CommonModel.Meta.indexes + [
            # Core relationship indexes
            models.Index(fields=["user", "is_deleted"]),  # User's addresses + manager
            models.Index(fields=["user", "is_default", "is_deleted"]),  # User's default address

            # Location-based indexes
            models.Index(fields=["country", "is_deleted"]),  # Regional analytics
            models.Index(fields=["city", "is_deleted"]),  # City-based queries
            models.Index(fields=["state", "is_deleted"]),  # State-based queries
            models.Index(fields=["zip_code", "is_deleted"]),  # Zip code lookups

            # Composite location indexes
            models.Index(fields=["country", "state", "city", "is_deleted"]),  # Full location queries
            models.Index(fields=["user", "country", "is_deleted"]),  # User's addresses by country

            # Default address quick lookup
            models.Index(fields=["is_default", "is_deleted"]),  # All default addresses
        ]
        constraints = [
            # Ensure only one default address per user
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_default=True, is_deleted=False),
                name='unique_default_shipping_address'
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

    def __str__(self):
        return self.email

    class Meta(AuthCommonModel.Meta):
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['email']
        indexes = AuthCommonModel.Meta.indexes + [
            # Critical authentication indexes
            models.Index(fields=['email']),  # Used in get_by_email() - case insensitive
            models.Index(fields=['is_deleted', 'email']),  # Default manager + email lookup

            # Manager-specific composite indexes
            models.Index(fields=['is_deleted', 'is_active']),  # Default manager + active/inactive
            models.Index(fields=['is_deleted', 'is_staff']),  # Admin queries
            models.Index(fields=['is_deleted', 'is_superuser']),  # Superuser queries

            # Performance for common operations
            models.Index(fields=['date_joined', 'is_deleted']),  # Analytics on active users
            models.Index(fields=['last_login', 'is_deleted']),  # Active user engagement
        ]


# Separate User model for user details
class Profile(CommonModel):
    objects = ProfileManager()

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
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
    phone_number = PhoneNumberField(unique=True)
    shipping_address = models.ForeignKey("ShippingAddress", on_delete=models.CASCADE,
                                         related_name="user_profile", null=True, blank=True)
    billing_address = models.ForeignKey("BillingAddress", on_delete=models.CASCADE,
                                        related_name="user_profile", null=True, blank=True)
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

    class Meta(CommonModel.Meta):
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
        ]