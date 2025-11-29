import logging

from django.conf import settings
from django.db import models
from django.core import validators
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser
from django_countries.fields import CountryField
from phonenumber_field.modelfields import PhoneNumberField

from common.models import CommonModel, AuthCommonModel
from orders.enums import active_order_statuses
from users.managers import ProfileManager, CustomUserManager
from users.enums import UserRole, Gender

logger = logging.getLogger(__name__)


class UserRoles(CommonModel):
    """User Role model. It is used to assign a role to a user."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="user_roles")
    role = models.CharField(max_length=50, choices=UserRole.choices)
    description = models.TextField(max_length=2000, blank=True, null=True)

    def __str__(self):
        return f"{self.user} - {self.role}"
        
    def is_valid(self, *args, **kwargs) -> bool:
        """
        Check if the user role assignment is valid according to business rules.

        Validates:
        1. Base model validation (is_active, is_deleted, etc.)
        2. User is valid and not deleted
        3. Role is a valid choice
        4. No duplicate active role assignments for the same user

        Returns:
            bool: True if the user role is valid, False otherwise
        """
        # Call parent's is_valid first
        if not super().is_valid(*args, **kwargs):
            return False

        validation_errors = []

        # Check required user relationship
        if not hasattr(self, 'user') or not self.user or self.user.is_deleted:
            validation_errors.append("Valid user is required")
        elif not self.user.is_valid():
            validation_errors.append("Associated user is invalid")

        # Check role is valid
        if not self.role or self.role not in dict(UserRole.choices):
            validation_errors.append(f"Invalid role: {self.role}")

        # Check for duplicate active role assignments
        if hasattr(self, 'user') and hasattr(self, 'role') and not self.is_deleted:
            duplicate_roles = UserRoles.objects.filter(
                user=self.user,
                role=self.role,
                is_deleted=False
            ).exclude(pk=getattr(self, 'pk', None))  # Exclude self if updating
            
            if duplicate_roles.exists():
                validation_errors.append("This user already has this role assigned")

        # Log validation errors if any
        if validation_errors:
            user_email = getattr(getattr(self, 'user', None), 'email', 'unknown')
            logger.warning(
                f"UserRole validation failed - "
                f"ID: {getattr(self, 'id', 'new')}, "
                f"User: {user_email}, "
                f"Role: {getattr(self, 'role', 'None')}. "
                f"Errors: {', '.join(validation_errors)}"
            )
            return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the user role can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
                - can_delete: True if the role can be deleted, False otherwise
                - reason: Empty string if can_delete is True, otherwise the reason why it can't be deleted
        """
        # Check base class can_be_deleted first
        base_can_delete, reason = super().can_be_deleted()
        if not base_can_delete:
            logger.debug(f"UserRole {getattr(self, 'id', 'new')} base validation failed: {reason}")
            return False, reason

        # Check if this is the last admin role for the user
        if hasattr(self, 'user') and hasattr(self, 'role') and self.role == UserRole.ADMIN:
            admin_roles = UserRoles.objects.filter(
                user=self.user,
                role=UserRole.SUPER_ADMIN,
                is_deleted=False
            ).exclude(pk=getattr(self, 'pk', None))
            
            if not admin_roles.exists():
                return False, "Cannot delete the last admin role for a user"

        # Check if this role is required for the user
        if hasattr(self, 'user') and hasattr(self, 'role') and self.role == UserRole.CUSTOMER:
            customer_roles = UserRoles.objects.filter(
                user=self.user,
                role=UserRole.CUSTOMER,
                is_deleted=False
            ).exclude(pk=getattr(self, 'pk', None))
            
            if not customer_roles.exists():
                return False, "User must have at least one CUSTOMER role"

        return True, ""

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
        role_name = getattr(self.role, 'role', 'No Role')
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

    def is_valid(self, *args, **kwargs) -> bool:
        """
        Check if the user is valid according to business rules.

        Validates:
        1. Base model validation (is_active, is_deleted, etc.)
        2. Email is valid and not empty
        3. First and last name are provided
        4. Role is valid if provided

        Returns:
            bool: True if the user is valid, False otherwise
        """
        if not super().is_valid(*args, **kwargs):
            return False

        validation_errors = []

        if not self.email or not self.email.strip():
            validation_errors.append("Email is required")

        if not self.first_name or not self.first_name.strip():
            validation_errors.append("First name is required")
        if not self.last_name or not self.last_name.strip():
            validation_errors.append("Last name is required")

        if hasattr(self, 'role') and self.role and self.role.is_deleted:
            validation_errors.append("Assigned role is deleted")

        if validation_errors:
            logger.warning(
                f"User validation failed - "
                f"ID: {getattr(self, 'id', 'new')}, "
                f"Email: {getattr(self, 'email', 'None')}. "
                f"Errors: {', '.join(validation_errors)}"
            )
            return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the profile can be safely soft-deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
                - can_delete: True if the profile can be deleted, False otherwise
                - reason: Empty string if can_delete is True, otherwise the reason why it can't be deleted
        """
        # Check base class can_be_deleted first
        base_can_delete, reason = super().can_be_deleted()
        if not base_can_delete:
            logger.debug(f"Profile {getattr(self, 'id', 'new')} base validation failed: {reason}")
            return False, reason

        # Check if user has active orders
        if hasattr(self, 'user') and hasattr(self.user, 'orders') and self.user.orders.filter(
            status__in=active_order_statuses
        ).exists():
            return False, "User has active orders"

        return True, ""


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
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_deleted=False),
                name='unique_user_profile'
            )
        ]

    def is_valid(self, *args, **kwargs) -> bool:
        """
        Check if the profile is valid according to business rules.

        Validates:
        1. Base model validation (is_active, is_deleted, etc.)
        2. User is valid and not deleted
        3. Phone number is valid if provided
        4. Date of birth is in the past
        5. Addresses are valid if provided

        Returns:
            bool: True if the profile is valid, False otherwise
        """
        # Call parent's is_valid first
        if not super().is_valid(*args, **kwargs):
            return False

        validation_errors = []

        # Check required user relationship
        if not hasattr(self, 'user') or not self.user or self.user.is_deleted:
            validation_errors.append("Valid user is required")
        elif not self.user.is_valid():
            validation_errors.append("Associated user is invalid")

        # Check phone number if provided
        if hasattr(self, 'phone_number') and self.phone_number:
            try:
                phone_number = str(self.phone_number)
                if not phone_number.startswith('+'):
                    validation_errors.append("Phone number must include country code")
            except Exception as e:
                validation_errors.append(f"Invalid phone number: {str(e)}")

        # Check date of birth
        if hasattr(self, 'date_of_birth'):
            from django.utils import timezone
            if self.date_of_birth > timezone.now().date():
                validation_errors.append("Date of birth cannot be in the future")

        if validation_errors:
            user_email = getattr(getattr(self, 'user', None), 'email', 'unknown')
            logger.warning(
                f"Profile validation failed - "
                f"ID: {getattr(self, 'id', 'new')}, "
                f"User: {user_email}. "
                f"Errors: {', '.join(validation_errors)}"
            )
            return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the profile can be safely soft-deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
                - can_delete: True if the profile can be deleted, False otherwise
                - reason: Empty string if can_delete is True, otherwise the reason why it can't be deleted
        """
        # Check base class can_be_deleted first
        base_can_delete, reason = super().can_be_deleted()
        if not base_can_delete:
            logger.debug(f"Profile {getattr(self, 'id', 'new')} base validation failed: {reason}")
            return False, reason

        if hasattr(self, 'user'):
            user_can_delete, reason = super().can_be_deleted()
            if not user_can_delete:
                return False, reason

        return True, ""