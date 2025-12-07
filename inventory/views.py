from rest_framework import viewsets, status, filters, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, F, Sum, Count

from common.mixins import SoftDeleteMixin
from common.permissions import IsStaffOrReadOnly
from inventory.models import WarehouseProfile, Inventory
from inventory.serializers import (
    WarehouseSerializer, 
    InventorySerializer,
    InventoryUpdateSerializer
)
from inventory.filters import InventoryFilter, WarehouseFilter


class WarehouseViewSet(SoftDeleteMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing warehouses.
    """
    queryset = WarehouseProfile.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_class = WarehouseFilter
    ordering_fields = ['name', 'city', 'country', 'current_utilization', 'date_created']
    search_fields = ['name', 'code', 'city', 'state', 'country', 'contact_email', 'contact_phone']
    ordering = ['name']

    def get_queryset(self):
        """
        Optionally filter warehouses by operational status and active fulfillment.
        """
        queryset = super().get_queryset()
        
        is_operational = self.request.query_params.get('is_operational')
        if is_operational is not None:
            queryset = queryset.filter(is_operational=is_operational.lower() == 'true')
            
        is_active_fulfillment = self.request.query_params.get('is_active_fulfillment')
        if is_active_fulfillment is not None:
            queryset = queryset.filter(is_active_fulfillment=is_active_fulfillment.lower() == 'true')
            
        warehouse_type = self.request.query_params.get('warehouse_type')
        if warehouse_type:
            queryset = queryset.filter(warehouse_type=warehouse_type)
            
        return queryset
    
    @action(detail=True, methods=['get'])
    def inventory(self, request, pk=None):
        """
        Get inventory for a specific warehouse.
        """
        warehouse = self.get_object()
        inventory = Inventory.objects.filter(warehouse=warehouse)
        
        product_id = request.query_params.get('product_id')
        if product_id:
            inventory = inventory.filter(product_variant__product_id=product_id)
            
        page = self.paginate_queryset(inventory)
        if page is not None:
            serializer = InventorySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = InventorySerializer(inventory, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def low_stock(self, request, pk=None):
        """
        Get low stock items for a specific warehouse.
        """
        warehouse = self.get_object()
        low_stock = Inventory.objects.filter(
            warehouse=warehouse,
            quantity_available__lte=F('reorder_level') * 1.5  # 1.5x reorder level as threshold
        ).order_by('quantity_available')
        
        page = self.paginate_queryset(low_stock)
        if page is not None:
            serializer = InventorySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = InventorySerializer(low_stock, many=True)
        return Response(serializer.data)


class InventoryViewSet(SoftDeleteMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     mixins.DestroyModelMixin,
                     mixins.ListModelMixin,
                     viewsets.GenericViewSet):
    """
    ViewSet for managing inventory.
    """
    queryset = Inventory.objects.select_related('product_variant', 'warehouse')
    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_class = InventoryFilter
    ordering_fields = [
        'quantity_available', 'quantity_reserved', 'last_restocked', 
        'product_variant__name', 'warehouse__name'
    ]
    search_fields = [
        'product_variant__name', 'product_variant__sku',
        'warehouse__name', 'warehouse__code', 'batch_number'
    ]
    ordering = ['-date_updated']

    def get_serializer_class(self):
        """
        Use different serializers for different actions.
        """
        if self.action in ['update', 'partial_update']:
            return InventoryUpdateSerializer
        return InventorySerializer

    def get_queryset(self):
        """
        Optionally filter inventory by various parameters.
        """
        queryset = super().get_queryset()
        
        variant_id = self.request.query_params.get('variant_id')
        if variant_id:
            queryset = queryset.filter(product_variant_id=variant_id)
            
        warehouse_id = self.request.query_params.get('warehouse_id')
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)
            
        stock_status = self.request.query_params.get('stock_status')
        if stock_status == 'in_stock':
            queryset = queryset.filter(quantity_available__gt=0)
        elif stock_status == 'out_of_stock':
            queryset = queryset.filter(quantity_available=0)
        elif stock_status == 'low_stock':
            queryset = queryset.filter(quantity_available__lte=F('reorder_level'))
            
        backorder = self.request.query_params.get('backorder')
        if backorder is not None:
            queryset = queryset.filter(is_backorder_allowed=backorder.lower() == 'true')
            
        return queryset
    
    @action(detail=True, methods=['post'])
    def adjust_stock(self, request, pk=None):
        """
        Adjust inventory quantity.
        """
        inventory = self.get_object()
        serializer = InventoryUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            adjustment = serializer.validated_data.get('adjustment')
            
            if adjustment is not None:
                # Create stock movement record here if needed
                # stock_movement = StockMovement.objects.create(...)
                pass
                
            serializer.update(inventory, serializer.validated_data)
            
            return Response(
                InventorySerializer(inventory).data,
                status=status.HTTP_200_OK
            )
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get inventory summary across all warehouses.
        """
        summary = Inventory.objects.aggregate(
            total_available=Sum('quantity_available'),
            total_reserved=Sum('quantity_reserved'),
            total_value=Sum(F('quantity_available') * F('cost_price'))
        )
        
        low_stock_count = Inventory.objects.filter(
            quantity_available__lte=F('reorder_level')
        ).count()
        
        out_of_stock_count = Inventory.objects.filter(
            quantity_available=0
        ).count()
        
        summary.update({
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'warehouse_count': WarehouseProfile.objects.count()
        })
        
        return Response(summary)


class InventoryByProductViewSet(SoftDeleteMixin, viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for getting inventory aggregated by product.
    """
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    
    def get_queryset(self):
        """
        Get inventory grouped by product variant.
        """
        return Inventory.objects.values(
            'product_variant_id', 
            'product_variant__name',
            'product_variant__sku'
        ).annotate(
            total_available=Sum('quantity_available'),
            total_reserved=Sum('quantity_reserved'),
            warehouse_count=Count('warehouse', distinct=True)
        ).order_by('product_variant__name')
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(product_variant__name__icontains=search) |
                Q(product_variant__sku__icontains=search)
            )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(page)
            
        return Response(queryset)


class InventoryByWarehouseViewSet(SoftDeleteMixin, viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for getting inventory aggregated by warehouse.
    """
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated, IsStaffOrReadOnly]
    
    def get_queryset(self):
        """
        Get inventory grouped by warehouse.
        """
        return Inventory.objects.values(
            'warehouse_id', 
            'warehouse__name',
            'warehouse__code'
        ).annotate(
            total_available=Sum('quantity_available'),
            total_reserved=Sum('quantity_reserved'),
            product_count=Count('product_variant', distinct=True),
            total_value=Sum(F('quantity_available') * F('cost_price'))
        ).order_by('warehouse__name')
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(warehouse__name__icontains=search) |
                Q(warehouse__code__icontains=search)
            )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(page)
            
        return Response(queryset)