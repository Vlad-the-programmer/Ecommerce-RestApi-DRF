from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django_countries.fields import CountryField

from common.models import CommonModel
from .enums import ShippingType, CarrierType
from .managers import ShippingClassManager, InternationalRateManager


class InternationalRate(CommonModel):
    objects = InternationalRateManager()

    country = CountryField(unique=True)
    surcharge = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return f"{self.country} - {self.surcharge}"

    class Meta:
        db_table = "international_rates"
        verbose_name = _("International Rate")
        verbose_name_plural = _("International Rates")
        ordering = ["country"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=["surcharge"]),
            models.Index(fields=['country', 'is_active', 'is_deleted']),
            models.Index(fields=['surcharge', 'is_active', 'is_deleted']),
            models.Index(fields=['country', 'is_active']),
            models.Index(fields=['surcharge', 'is_active']),

        ]
        constraints = [
            models.CheckConstraint(check=models.Q(surcharge__gte=0), name="non_negative_surcharge")
        ]

    def is_valid(self) -> bool:
        """
        Check if the international rate is valid according to business rules.

        Returns:
            bool: True if the international rate is valid, False otherwise
        """
        if not super().is_valid():
            return False

        if not all([self.country, self.surcharge is not None]):
            return False

        if self.surcharge < 0:
            return False

        if not self.pk:
            if InternationalRate.objects.filter(country=self.country).exists():
                return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the international rate can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        if ShippingClass.objects.filter(available_countries__contains=[self.country]).exists():
            return False, "Cannot delete rate used by active shipping classes"

        return True, ""


class ShippingClass(CommonModel):
    """
    Shipping class for defining shipping methods, costs, and delivery estimates.
    """

    objects = ShippingClassManager()

    name = models.CharField(
        max_length=100,
        verbose_name=_("Shipping Class Name"),
        help_text=_("Descriptive name for this shipping class (e.g., 'Standard Ground', 'Express 2-Day')")
    )

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Customer"),
        help_text=_("Customer who created this shipping class")
    )

    shipping_address = models.ForeignKey(
        'common.ShippingAddress',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Shipping Address"),
        help_text=_("Shipping address for this shipping class")
    )
    shipping_notes = models.TextField(
        blank=True,
        max_length=4000,
        verbose_name=_("Shipping Notes"),
        help_text=_("Internal notes, carrier instructions, or special handling requirements")
    )

    base_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("Base Shipping Cost"),
        help_text=_("Base cost for shipping before any weight or distance adjustments"),
        validators=[MinValueValidator(0)]
    )

    shipping_type = models.CharField(
        max_length=100,
        choices=ShippingType.choices,
        default=ShippingType.STANDARD,
        verbose_name=_("Shipping Type"),
        help_text=_("Type of shipping service offered")
    )

    carrier_type = models.CharField(
        max_length=50,
        choices=CarrierType.choices,
        default=CarrierType.IN_HOUSE,
        verbose_name=_("Carrier Type"),
        help_text=_("Shipping carrier or service provider")
    )

    estimated_days_min = models.PositiveIntegerField(
        verbose_name=_("Minimum Estimated Days"),
        help_text=_("Minimum number of business days for delivery"),
        validators=[MinValueValidator(0), MaxValueValidator(365)]
    )

    estimated_days_max = models.PositiveIntegerField(
        verbose_name=_("Maximum Estimated Days"),
        help_text=_("Maximum number of business days for delivery"),
        validators=[MinValueValidator(1), MaxValueValidator(365)]
    )

    # Additional cost fields
    cost_per_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Cost per Kilogram"),
        help_text=_("Additional cost per kilogram over base weight"),
        validators=[MinValueValidator(0)]
    )

    free_shipping_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=0.00,
        verbose_name=_("Free Shipping Threshold"),
        help_text=_("Order total required for free shipping (leave empty if not applicable)")
    )

    max_weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Maximum Weight (kg)"),
        help_text=_("Maximum weight allowed for this shipping class in kilograms")
    )

    max_dimensions = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Maximum Dimensions"),
        help_text=_("Maximum package dimensions (L×W×H in cm) for this shipping class")
    )

    # Service features
    tracking_available = models.BooleanField(
        default=True,
        verbose_name=_("Tracking Available"),
        help_text=_("Whether tracking is available for this shipping method")
    )

    signature_required = models.BooleanField(
        default=False,
        verbose_name=_("Signature Required"),
        help_text=_("Whether signature is required upon delivery")
    )

    insurance_included = models.BooleanField(
        default=False,
        verbose_name=_("Insurance Included"),
        help_text=_("Whether basic insurance is included in the shipping cost")
    )

    insurance_cost = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Additional Insurance Cost"),
        help_text=_("Cost for additional insurance coverage")
    )

    # Regional restrictions
    domestic_only = models.BooleanField(
        default=True,
        verbose_name=_("Domestic Only"),
        help_text=_("Whether this shipping method is for domestic deliveries only")
    )

    available_countries = CountryField(
        multiple=True,
        blank=True,
        verbose_name=_("Available Countries"),
        help_text=_("Countries where this shipping method is available")
    )

    handling_time_days = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Handling Time (Days)"),
        help_text=_("Number of business days needed to process order before shipping"),
        validators=[MinValueValidator(0), MaxValueValidator(14)]
    )

    def __str__(self):
        return f"{self.name} ({self.get_shipping_type_display()})"

    class Meta:
        db_table = "shipping_classes"
        verbose_name = _("Shipping Class")
        verbose_name_plural = _("Shipping Classes")
        ordering = ["base_cost", "estimated_days_min"]
        indexes = CommonModel.Meta.indexes + [
            models.Index(fields=['shipping_type', 'is_deleted', 'is_active']),
            models.Index(fields=['carrier_type', 'is_deleted', 'is_active']),
            models.Index(fields=['free_shipping_threshold', 'is_deleted', 'is_active']),
            models.Index(fields=['domestic_only', 'is_active', 'is_deleted']),
            models.Index(fields=['shipping_type', 'carrier_type', 'is_active', 'is_deleted']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(estimated_days_min__lte=models.F('estimated_days_max')),
                name='valid_estimated_days_range'
            ),
            models.CheckConstraint(
                check=models.Q(base_cost__gt=0),
                name='non_negative_greater_than_zero_base_cost'
            ),
            models.CheckConstraint(
                check=models.Q(max_weight_kg__gt=0),
                name='non_negative_greater_than_zero_max_weight_kg'
            ),
            models.CheckConstraint(
                check=models.Q(insurance_cost__gte=0),
                name='non_negative_insurance_cost'
            ),
            models.CheckConstraint(
                check=models.Q(free_shipping_threshold__gte=0),
                name='non_negative_free_shipping_threshold'
            ),
        ]


    def get_estimated_delivery(self) -> str:
        """Get formatted estimated delivery timeframe"""
        if self.estimated_days_min == self.estimated_days_max:
            return _("%(days)s business days") % {'days': self.estimated_days_min}
        return _("%(min)s-%(max)s business days") % {
            'min': self.estimated_days_min,
            'max': self.estimated_days_max
        }

    def get_total_delivery_time(self) -> str:
        """Get total delivery time including handling"""
        total_min = self.handling_time_days + self.estimated_days_min
        total_max = self.handling_time_days + self.estimated_days_max

        if total_min == total_max:
            return _("%(days)s business days total") % {'days': total_min}
        return _("%(min)s-%(max)s business days total") % {
            'min': total_min,
            'max': total_max
        }

    def calculate_order_weight(self, order) -> float:
        """
        Calculate total order weight in kilograms for a SPECIFIC order.

        Args:
            order: The Order instance to calculate weight for

        Returns:
            Total weight in kilograms
        """
        total_weight = 0.0
        for item in order.order_items.all():
            if item.variant and item.variant.weight:
                total_weight += float(item.variant.weight) * item.quantity
            elif item.product and item.product.weight:
                total_weight += float(item.product.weight) * item.quantity
        return total_weight

    def calculate_shipping_cost(self, order_total: float = 0,
                                destination_country_code: str = None) -> float:
        """
        Calculate shipping cost based on weight, order total, and destination.

        Args:
            weight_kg: Package weight in kilograms
            order_total: Total order amount for free shipping threshold
            destination_country_code: Destination country code for international rates

        Returns:
            Calculated shipping cost
        """
        if (self.free_shipping_threshold and
                order_total >= float(self.free_shipping_threshold)):
            return 0.0

        total_cost = float(self.base_cost)

        if self.calculate_order_weight() > 0 and self.cost_per_kg > 0:
            total_cost += float(self.cost_per_kg) * self.calculate_order_weight()

        if destination_country_code and self.shipping_type == ShippingType.INTERNATIONAL:
            international_surcharge = self._get_international_surcharge(destination_country_code)
            total_cost += international_surcharge

        if not self.insurance_included and self.insurance_cost > 0:
            total_cost += float(self.insurance_cost)

        return round(total_cost, 2)

    def _get_international_surcharge(self, country_code: str) -> Optional[Decimal]:
        """Get international surcharge for specific country"""
        rate = InternationalRate.objects.filter(country=country_code, is_active=True, is_deleted=False).first()
        return rate.surcharge if rate else Decimal('0.00')

    def can_ship_to_country(self, country_code: str) -> bool:
        """Check if this shipping class can ship to a specific country"""
        return self.available_countries.filter(
            code=country_code,
        ).exists()

    def get_order_total(self):
        return self.orders.aggregate(total=Sum('total_amount'))['total']

    def get_shipping_total_cost(self):
        return self.calculate_shipping_cost(self.get_order_total(), self.shipping_address.country_code)

    def can_ship_item(self, weight_kg: float = 0, dimensions: str = None, destination_country_code: str = None) -> \
    tuple[bool, str]:
        """
        Check if an item can be shipped with this shipping class.

        Args:
            weight_kg: Item weight in kilograms
            dimensions: Item dimensions in L×W×H format
            destination_country_code: Destination country code

        Returns:
            Tuple of (can_ship: bool, reason: str)
        """
        if not self.is_active:
            return False, _("Shipping class is not active")

        if destination_country_code and not self.can_ship_to_country(destination_country_code):
            return False, _("Shipping not available to this country")

        if self.max_weight_kg and weight_kg > float(self.max_weight_kg):
            return False, _("Item exceeds maximum weight limit")

        if dimensions and self.max_dimensions:
            # Basic dimension validation could be added
            pass

        return True, _("Item can be shipped")

    @property
    def is_free_shipping_available(self) -> bool:
        """Check if free shipping is available with this class"""
        return self.free_shipping_threshold is not None

    @property
    def delivery_speed(self) -> str:
        """Categorize delivery speed"""
        avg_days = (self.estimated_days_min + self.estimated_days_max) / 2

        if avg_days <= 1:
            return "overnight"
        elif avg_days <= 3:
            return "express"
        elif avg_days <= 7:
            return "standard"
        else:
            return "economy"

    @property
    def available_countries_list(self) -> list:
        """Get list of available country codes"""
        return list(self.available_countries.values_list('code', flat=True))

    @property
    def is_international(self) -> bool:
        """Check if this is an international shipping class"""
        return self.shipping_type == ShippingType.INTERNATIONAL

    @property
    def service_features(self) -> dict:
        """Get dictionary of service features"""
        return {
            'tracking': self.tracking_available,
            'signature_required': self.signature_required,
            'insurance_included': self.insurance_included,
            'insurance_cost': float(self.insurance_cost),
            'handling_time': self.handling_time_days,
            'free_shipping_available': self.is_free_shipping_available,
            'free_shipping_threshold': float(self.free_shipping_threshold) if self.free_shipping_threshold else None,
            'available_countries': self.available_countries,
            'domestic_only': self.domestic_only,
        }

    def get_shipping_details(self) -> dict:
        """Get comprehensive shipping details"""
        return {
            'name': self.name,
            'type': self.get_shipping_type_display(),
            'carrier': self.get_carrier_type_display(),
            'base_cost': float(self.base_cost),
            'cost_per_kg': float(self.cost_per_kg),
            'estimated_delivery': self.get_estimated_delivery(),
            'total_delivery_time': self.get_total_delivery_time(),
            'delivery_speed': self.delivery_speed,
            'features': self.service_features,
            'restrictions': {
                'max_weight_kg': float(self.max_weight_kg) if self.max_weight_kg else None,
                'max_dimensions': self.max_dimensions,
                'domestic_only': self.domestic_only,
                'available_countries': self.available_countries.filter(is_active=True),
            }
        }

    def is_valid(self) -> bool:
        """
        Check if the shipping class is valid according to business rules.

        Returns:
            bool: True if the shipping class is valid, False otherwise
        """
        if not super().is_valid():
            return False

        required_fields = [
            self.name,
            self.base_cost is not None,
            self.shipping_type in dict(ShippingType.choices),
            self.carrier_type in dict(CarrierType.choices),
            self.estimated_days_min is not None,
            self.estimated_days_max is not None,
            self.cost_per_kg is not None,
            self.handling_time_days is not None
        ]

        if not all(required_fields):
            return False

        if any([
            self.base_cost < 0,
            self.cost_per_kg < 0,
            self.insurance_cost < 0,
            self.handling_time_days < 0,
            self.estimated_days_min < 0,
            self.estimated_days_max < 1,
            self.estimated_days_min > self.estimated_days_max
        ]):
            return False

        if self.max_weight_kg is not None and self.max_weight_kg <= 0:
            return False

        if self.free_shipping_threshold is not None and self.free_shipping_threshold < 0:
            return False

        if self.shipping_type == ShippingType.INTERNATIONAL and not self.available_countries.exists():
            return False

        return True

    def can_be_deleted(self) -> tuple[bool, str]:
        """
        Check if the shipping class can be safely deleted.

        Returns:
            tuple: (can_delete: bool, reason: str)
        """
        can_delete, reason = super().can_be_deleted()
        if not can_delete:
            return False, reason

        from orders.models import Order
        if Order.objects.filter(shipping_class=self).exists():
            return False, "Cannot delete shipping class with associated orders"

        if self.is_active and not ShippingClass.objects.filter(
            shipping_type=self.shipping_type,
        ).exclude(pk=self.pk).exists():
            return False, f"Cannot delete the only active {self.get_shipping_type_display()} shipping class"

        return True, ""

    def clean(self):
        """Validate shipping class data"""
        from django.core.exceptions import ValidationError

        super().clean()

        if self.estimated_days_min > self.estimated_days_max:
            raise ValidationError({
                'estimated_days_min': _("Minimum estimated days cannot be greater than maximum estimated days")
            })

        if self.free_shipping_threshold and self.free_shipping_threshold <= 0:
            raise ValidationError({
                'free_shipping_threshold': _("Free shipping threshold must be greater than 0")
            })

        if self.max_weight_kg and self.max_weight_kg <= 0:
            raise ValidationError({
                'max_weight_kg': _("Maximum weight must be greater than 0")
            })
