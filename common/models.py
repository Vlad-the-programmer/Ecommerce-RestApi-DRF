import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.managers import NonDeletedObjectsManager


class CommonModel(models.Model):
    objects = NonDeletedObjectsManager()
    all_objects = models.Manager()

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True, db_index=True)
    date_updated = models.DateTimeField(auto_now=True, null=True)
    date_deleted = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(verbose_name=_('Active'), default=True, db_index=True)
    is_deleted = models.BooleanField(verbose_name=_('Deleted'), default=False, db_index=True)

    class Meta:
        abstract = True
        indexes = [
            # Core manager patterns (used in ALL queries)
            models.Index(fields=['is_deleted']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_deleted', 'is_active']),

            # Date-based queries (common for reporting and cleanup)
            models.Index(fields=['date_created', 'is_deleted']),
            models.Index(fields=['is_deleted', 'date_deleted']),

            # Combined date and status queries
            models.Index(fields=['date_created', 'is_active', 'is_deleted']),

        ]


class AuthCommonModel(CommonModel):
    """CommonModel without date_created for user auth model that have date_joined."""

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['is_deleted']),
            models.Index(fields=['is_deleted', 'is_active']),
            models.Index(fields=['is_deleted', 'date_deleted']),
        ]

    date_created = None