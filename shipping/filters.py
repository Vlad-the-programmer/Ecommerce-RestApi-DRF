import django_filters
from django.db.models import Q
from .models import ShippingClass
from .enums import ShippingType, CarrierType


class ShippingClassFilter(django_filters.FilterSet):
    """
    Filter for ShippingClassViewSet to support advanced filtering.
    """
    name = django_filters.CharFilter(lookup_expr='icontains')
    min_cost = django_filters.NumberFilter(field_name='base_cost', lookup_expr='gte')
    max_cost = django_filters.NumberFilter(field_name='base_cost', lookup_expr='lte')
    shipping_type = django_filters.MultipleChoiceFilter(
        field_name='shipping_type',
        choices=ShippingType.choices
    )
    carrier_type = django_filters.MultipleChoiceFilter(
        field_name='carrier_type',
        choices=CarrierType.choices
    )
    has_free_shipping = django_filters.BooleanFilter(
        method='filter_has_free_shipping',
        label='Has Free Shipping'
    )
    max_delivery_days = django_filters.NumberFilter(
        method='filter_max_delivery_days',
        label='Maximum Delivery Days'
    )
    country = django_filters.CharFilter(
        method='filter_by_country',
        help_text='Filter by available country (ISO 3166-1 alpha-2 code)'
    )

    class Meta:
        model = ShippingClass
        fields = {
            'name': ['exact', 'icontains'],
            'base_cost': ['exact', 'lt', 'gt', 'lte', 'gte'],
            'shipping_type': ['exact', 'in'],
            'carrier_type': ['exact', 'in'],
            'estimated_days_min': ['exact', 'lt', 'gt', 'lte', 'gte'],
            'estimated_days_max': ['exact', 'lt', 'gt', 'lte', 'gte'],
            'is_active': ['exact'],
            'domestic_only': ['exact'],
            'tracking_available': ['exact'],
            'signature_required': ['exact'],
            'insurance_included': ['exact'],
        }

    def filter_has_free_shipping(self, queryset, name, value):
        """
        Filter shipping classes based on whether they offer free shipping.
        """
        if value:
            return queryset.exclude(free_shipping_threshold__isnull=True)
        return queryset.filter(free_shipping_threshold__isnull=True)

    def filter_max_delivery_days(self, queryset, name, value):
        """
        Filter shipping classes with estimated_days_max less than or equal to the given value.
        """
        try:
            max_days = int(value)
            return queryset.filter(estimated_days_max__lte=max_days)
        except (ValueError, TypeError):
            return queryset.none()

    def filter_by_country(self, queryset, name, value):
        """
        Filter shipping classes that can ship to the specified country.
        """
        if not value:
            return queryset
            
        return queryset.filter(
            Q(domestic_only=True) | 
            Q(available_countries__contains=[value])
        )

    @property
    def qs(self):
        """
        Override to apply default filtering and ordering.
        """
        qs = super().qs
            
        return qs.distinct()
