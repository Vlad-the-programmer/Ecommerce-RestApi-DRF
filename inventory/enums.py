
from django.utils.translation import gettext_lazy as _
from django.db.models import TextChoices


class WAREHOUSE_TYPE(TextChoices):
    MAIN = 'main', _("Main")
    REGIONAL = 'regional', _("Regional")
    STORE = 'store', _("Store")
    DROP_SHIP = 'drop_ship', _("Drop-ship")