import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.managers import NonDeletedObjectsManager


class CommonModel(models.Model):
    objects = NonDeletedObjectsManager()
    all_objects = models.Manager()

    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True)
    date_updated = models.DateTimeField(auto_now=True, null=True)
    date_deleted = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(verbose_name=_('Active'), default=True, db_index=True)
    is_deleted = models.BooleanField(verbose_name=_('Deleted'), default=False, db_index=True)

    class Meta:
        abstract = True
        indexes = [
            # Basic single field indexes
            models.Index(fields=['uuid']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_deleted']),
            models.Index(fields=['date_created']),
            models.Index(fields=['date_updated']),

            # Composite indexes for common query patterns
            models.Index(fields=['is_active', 'is_deleted']),
            models.Index(fields=['date_created', 'is_active']),
            models.Index(fields=['is_active', 'date_updated']),

            # For soft delete queries
            models.Index(fields=['is_deleted', 'date_deleted']),
        ]

    def delete(self, *args, **kwargs):
        """
        Soft delete both profile and user.
        """
        from django.utils import timezone

        # Soft delete user
        self.is_active = False
        self.is_deleted = True
        self.date_deleted = timezone.now()
        self.save()

    def hard_delete(self, *args, **kwargs):
        """Actually delete the profile from database."""
        super().delete(*args, **kwargs)
