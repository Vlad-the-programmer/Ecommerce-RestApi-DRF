from django.db import models


class SoftDeleteManger(models.Manager):
    """Default queryset excludes soft deleted objects."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def with_deleted(self):
        """Return all objects including soft-deleted ones"""
        return super().get_queryset()