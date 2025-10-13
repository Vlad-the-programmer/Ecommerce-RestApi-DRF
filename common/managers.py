from django.db import models


class NonDeletedObjectsManager(models.Manager):
    """Default queryset excludes soft deleted objects."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)