import re
from psycopg2 import IntegrityError

from django.contrib.auth.models import BaseUserManager
from django.utils.translation import gettext_lazy as _

from common.managers import NonDeletedObjectsManager
from users.enums import UserRole, user_roles_descriptions


class CustomUserManager(BaseUserManager):
    """
    Enhanced custom user manager with email authentication and soft delete support.
    """

    def get_queryset(self):
        """Default queryset excludes soft deleted users."""
        return super().get_queryset().select_related('profile').filter(is_deleted=False)

    def normalize_email(self, email):
        """
        Normalize email address by lowercasing and cleaning.
        """
        email = super().normalize_email(email)
        return email.lower().strip()

    def validate_email(self, email):
        """Validate email format."""
        if not email:
            raise ValueError(_('The Email field must be set'))

        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise ValueError(_('Enter a valid email address.'))

        return self.normalize_email(email)

    def generate_username(self, email):
        """Generate a unique username from email."""
        base_username = email.split('@')[0]
        username = base_username

        # Ensure username is unique
        counter = 1
        while self.model.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        return username

    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given email and password.
        """
        from users.models import UserRoles

        # Validate and normalize email
        email = self.validate_email(email)

        # Auto-generate username if not provided
        if not extra_fields.get('username'):
            extra_fields['username'] = self.generate_username(email)

        # Validate required fields
        if not extra_fields.get('first_name'):
            raise ValueError(_('The First Name field must be set'))
        if not extra_fields.get('last_name'):
            raise ValueError(_('The Last Name field must be set'))

        user = self.model(email=email, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)

        # Create a UserRole
        role = (
            UserRole.SUPER_ADMIN if user.is_superuser
            else UserRole.EMPLOYEE if user.is_staff
            else UserRole.CUSTOMER
        )

        description = user_roles_descriptions.get(role, "Default role description")

        try:
            user_role = UserRoles.objects.create(user=user, role=role, description=description)
            user.role = user_role
            user.save()
        except IntegrityError:
            # Handle duplicate role
            # A UserRoles entry with the same user and role already exists and is not marked as deleted.
            pass
        except (ValueError, KeyError) as e:
            # Handle invalid data
            # user_roles_descriptions doesn't have a key for the given role or role is not valid.
            pass

        return user

    def create_user(self, email, password=None, **extra_fields):
        """
        Create a regular user with the given email and password.
        """
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('is_active', True)

        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create a superuser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self._create_user(email, password, **extra_fields)

    # Soft delete related methods
    def with_deleted(self):
        """Return a queryset that includes soft-deleted users."""
        return super().get_queryset()

    def deleted(self):
        """Return only soft-deleted users."""
        return super().get_queryset().filter(is_deleted=True)

    def active(self):
        """Return only active, non-deleted users."""
        return self.get_queryset().filter(is_active=True)

    def inactive(self):
        """Return only inactive, non-deleted users."""
        return self.get_queryset().filter(is_active=False)

    # Email-based queries
    def get_by_email(self, email):
        """Get user by email (case-insensitive)."""
        return self.get_queryset().get(email__iexact=email)

    def filter_by_domain(self, domain):
        """Filter users by email domain."""
        return self.get_queryset().filter(email__iendswith=f'@{domain}')

    # Bulk operations
    def bulk_soft_delete(self, queryset=None):
        """Soft delete multiple users."""
        from django.utils import timezone

        if queryset is None:
            queryset = self.get_queryset()

        return queryset.update(
            is_active=False,
            is_deleted=True,
            date_deleted=timezone.now()
        )


class ProfileManager(NonDeletedObjectsManager):
    def get_queryset(self):
        return (super().get_queryset()
                    .select_related('user'))