import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class CommonModel(models.Model):
    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    date_created = models.DateTimeField(auto_now_add=True, null=True)
    date_updated = models.DateTimeField(auto_now=True, null=True)
    is_active = models.BooleanField(verbose_name=_('Active'), default=True, db_index=True)

    class Meta:
        abstract = True
