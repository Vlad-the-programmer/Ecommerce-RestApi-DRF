import django_filters
from django.db import models
from django.utils.translation import gettext_lazy as _

from orders.models import Order, OrderItem, OrderStatusHistory, OrderTax
from orders.enums import OrderStatuses


class OrderFilter(django_filters.FilterSet):
    created_after = django_filters.DateFilter(
        field_name='date_created', 
        lookup_expr='gte',
        label=_('Created after (YYYY-MM-DD)'),
    )
    created_before = django_filters.DateFilter(
        field_name='date_created',
        lookup_expr='lte',
        label=_('Created before (YYYY-MM-DD)'),
    )
    
    status = django_filters.MultipleChoiceFilter(
        field_name='status',
        choices=OrderStatuses.choices,
        label=_('Order Status'),
    )
    
    min_total = django_filters.NumberFilter(
        field_name='total_amount', 
        lookup_expr='gte',
        label=_('Minimum total amount'),
    )
    max_total = django_filters.NumberFilter(
        field_name='total_amount', 
        lookup_expr='lte',
        label=_('Maximum total amount'),
    )
    
    user = django_filters.NumberFilter(
        field_name='user__id',
        label=_('User ID'),
    )
    
    search = django_filters.CharFilter(
        method='filter_search',
        label=_('Search by order number, email, or username'),
    )
    
    class Meta:
        model = Order
        fields = {
            'order_number': ['exact', 'icontains'],
            'status': ['exact'],
            'user__email': ['exact', 'icontains'],
            'user__username': ['exact', 'icontains'],
            'shipping_address__city': ['exact', 'icontains'],
            'shipping_address__country': ['exact'],
        }
    
    def filter_search(self, queryset, name, value):
        """Search by order number, user email, or username"""
        return queryset.filter(
            models.Q(order_number__icontains=value) |
            models.Q(user__email__icontains=value) |
            models.Q(user__username__icontains=value)
        )


class OrderItemFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name='product__id')
    variant = django_filters.NumberFilter(field_name='variant__id')
    order = django_filters.NumberFilter(field_name='order__id')
    
    class Meta:
        model = OrderItem
        fields = {
            'product': ['exact'],
            'variant': ['exact'],
            'order': ['exact'],
            'quantity': ['exact', 'gt', 'lt'],
            'total_price': ['exact', 'gt', 'lt'],
        }


class OrderStatusHistoryFilter(django_filters.FilterSet):
    order = django_filters.NumberFilter(field_name='order__id')
    status = django_filters.ChoiceFilter(
        field_name='status',
        choices=OrderStatuses.choices,
    )
    
    class Meta:
        model = OrderStatusHistory
        fields = {
            'order': ['exact'],
            'status': ['exact'],
            'changed_by': ['exact'],
            'date_created': ['exact', 'gt', 'lt', 'gte', 'lte'],
        }


class OrderTaxFilter(django_filters.FilterSet):
    order = django_filters.NumberFilter(field_name='order__id')
    tax = django_filters.NumberFilter(field_name='tax__id')
    rate_lte = django_filters.NumberFilter(field_name='rate', lookup_expr='lte')
    rate_gte = django_filters.NumberFilter(field_name='rate', lookup_expr='gte')

    class Meta:
        model = OrderTax
        fields = {
            'order': ['exact'],
            'tax': ['exact'],
            'rate_lte': ['lte'],
            'rate_gte': ['gte'],
        }