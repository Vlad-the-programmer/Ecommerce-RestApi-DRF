from rest_framework import status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.translation import gettext_lazy as _
from django_countries import countries

from common.permissions import IsStaffOrReadOnly
from .models import InternationalRate, ShippingClass
from .filters import ShippingClassFilter
from .serializers import ShippingClassSerializer, InternationalRateSerializer


class InternationalRateViewSet(SoftDeleteMixin, ModelViewSet):
    """
    API endpoint for managing international shipping rates.
    """
    queryset = InternationalRate.objects.all()
    serializer_class = InternationalRateSerializer
    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['country', 'surcharge', 'is_active']
    search_fields = ['country__name', 'country__code']
    ordering_fields = ['country', 'surcharge', 'date_created']
    ordering = ['country']

    def get_queryset(self):
        """
        Optionally filter by active status if 'active_only' query parameter is provided.
        """
        queryset = super().get_queryset()
        active_only = self.request.query_params.get('active_only', '').lower() == 'true'
        if active_only:
            queryset = queryset.all()
        return queryset

    @action(detail=False, methods=['get'])
    def countries_available(self, request):
        """
        Get a list of all available countries for international shipping.
        """
        country_codes = set(
            InternationalRate.objects.values_list('country', flat=True)
        )
        available_countries = [
            {'code': code, 'name': name}
            for code, name in dict(countries).items()
            if code in country_codes
        ]
        return Response(available_countries)


class ShippingClassViewSet(SoftDeleteMixin, ModelViewSet):
    """
    API endpoint for managing shipping classes.
    """
    queryset = ShippingClass.objects.all()
    serializer_class = ShippingClassSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ShippingClassFilter
    search_fields = ['name', 'shipping_notes', 'shipping_type', 'carrier_type']
    ordering_fields = [
        'name', 'base_cost', 'estimated_days_min', 
        'estimated_days_max', 'date_created'
    ]
    ordering = ['name']

    def get_permissions(self):
        """
        Only allow admin users to modify shipping classes.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        """
        Optionally filter by active status and shipping type.
        """
        queryset = super().get_queryset()
        shipping_type = self.request.query_params.get('shipping_type')
        country = self.request.query_params.get('country')
        
        if shipping_type:
            queryset = queryset.filter(shipping_type=shipping_type)
        
        if country:
            queryset = queryset.filter(available_countries__contains=[country])
        
        return queryset.distinct()

    @action(detail=False, methods=['get'])
    def shipping_options(self, request):
        """
        Get available shipping options for a specific order.
        Expected query parameters:
        - country: The destination country code (required)
        - order_total: The total order amount (optional, for free shipping calculation)
        """
        country = request.query_params.get('country')
        if not country:
            return Response(
                {'detail': _('Country code is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            order_total = float(request.query_params.get('order_total', 0))
        except (TypeError, ValueError):
            order_total = 0

        shipping_options = []
        queryset = self.get_queryset().all()
        
        for shipping_class in queryset:
            if not shipping_class.can_ship_to_country(country):
                continue
            
            cost = shipping_class.calculate_shipping_cost(
                order_total=order_total,
                destination_country_code=country
            )
            
            serializer = self.get_serializer(shipping_class)
            option_data = serializer.data
            option_data['cost'] = cost
            
            shipping_options.append(option_data)
        
        return Response(shipping_options)

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def toggle_active(self, request, pk=None):
        """
        Toggle the active status of a shipping class.
        Only available to admin users.
        """
        
        shipping_class = self.get_object()
        shipping_class.is_active = not shipping_class.is_active
        shipping_class.save(update_fields=['is_active', 'date_updated'])
        
        return Response({
            'id': shipping_class.id,
            'name': shipping_class.name,
            'is_active': shipping_class.is_active
        })
