from django.db import models
from common.middleware import get_current_user


class SoftDeleteManager(models.Manager):
    """Default queryset excludes soft deleted objects."""
    def get_queryset(self):
        """Get queryset with default filters"""
        user = get_current_user()

        if user and user.is_staff:
            return super().get_queryset()

        return super().get_queryset().filter(is_deleted=False, is_active=True)

    def active(self):
        """Get active objects"""
        return self.get_queryset().filter(is_active=True)

    def with_deleted(self):
        """Return all objects including soft-deleted ones"""
        return super().get_queryset()

    def only_deleted(self):
        """Return only soft-deleted objects"""
        return super().get_queryset().filter(is_deleted=True)

    def get(self, *args, **kwargs):
        """Get single object, automatically excludes deleted"""
        return self.get_queryset().get(*args, **kwargs)
