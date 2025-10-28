from django.utils.translation import gettext_lazy as _
from django.db.models import TextChoices


class ShippingType(TextChoices):
    STANDARD = 'standard', _('Standard Shipping')
    EXPRESS = 'express', _('Express Shipping')
    OVERNIGHT = 'overnight', _('Overnight Shipping')
    INTERNATIONAL = 'international', _('International Shipping')
    FREE = 'free', _('Free Shipping')
    PICKUP = 'pickup', _('Store Pickup')
    HEAVY = 'heavy', _('Heavy Item Shipping')
    REFRIGERATED = 'refrigerated', _('Refrigerated Shipping')


class CarrierType(TextChoices):
    UPS = 'ups', _('UPS')
    FEDEX = 'fedex', _('FedEx')
    DHL = 'dhl', _('DHL')
    DPD = 'dpd', _('DPD')
    INPOST = 'inpost', _('InPost')
    USPS = 'usps', _('USPS')
    LOCAL_COURIER = 'local_courier', _('Local Courier')
    IN_HOUSE = 'in_house', _('In-House Delivery')
    THIRD_PARTY = 'third_party', _('Third Party Logistics')

