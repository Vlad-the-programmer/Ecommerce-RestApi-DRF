import django_filters
from django.db.models import Q, F
from .models import Product
from .enums import ProductStatus, StockStatus, ProductLabel, ProductType


class ProductFilter(django_filters.FilterSet):
    """
    Filter for products with support for multiple filters and search.
    """
    min_price = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price', lookup_expr='lte')
    category = django_filters.NumberFilter(field_name='category__id')
    subcategory = django_filters.NumberFilter(field_name='subcategories__id')
    status = django_filters.MultipleChoiceFilter(
        field_name='status',
        choices=ProductStatus.choices
    )
    stock_status = django_filters.MultipleChoiceFilter(
        field_name='stock_status',
        choices=StockStatus.choices
    )
    label = django_filters.MultipleChoiceFilter(
        field_name='label',
        choices=ProductLabel.choices
    )
    product_type = django_filters.MultipleChoiceFilter(
        field_name='product_type',
        choices=ProductType.choices
    )
    search = django_filters.CharFilter(method='filter_search')
    
    class Meta:
        model = Product
        fields = {
            'price': ['lt', 'gt', 'lte', 'gte'],
            'date_created': ['lt', 'gt', 'lte', 'gte', 'exact'],
            'date_updated': ['lt', 'gt', 'lte', 'gte', 'exact'],
        }
    
    def filter_search(self, queryset, name, value):
        """
        Search across multiple fields with improved query performance.
        """
        if not value:
            return queryset
            
        return queryset.filter(
            Q(product_name__icontains=value) |
            Q(sku__iexact=value) |
            Q(barcode__iexact=value) |
            Q(product_description__icontains=value) |
            Q(category__name__icontains=value) |
            Q(subcategories__name__icontains=value)
        ).distinct()
    
    def filter_queryset(self, queryset):
        """
        Apply all filters with optimizations.
        """
        queryset = super().filter_queryset(queryset)
        
        params = self.form.cleaned_data
        
        if params.get('in_stock') is not None:
            if params['in_stock']:
                queryset = queryset.filter(stock_status=StockStatus.IN_STOCK)
        
        if params.get('on_sale') is not None:
            if params['on_sale']:
                queryset = queryset.filter(
                    compare_at_price__gt=F('price')
                )
        
        if params.get('featured') is not None:
            if params['featured']:
                from django.utils import timezone
                queryset = queryset.filter(
                    Q(label=ProductLabel.FEATURED) |
                    Q(featured_until__gte=timezone.now())
                )
        
        return queryset.distinct()
