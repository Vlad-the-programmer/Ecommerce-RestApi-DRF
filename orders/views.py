from rest_framework import status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.utils.translation import gettext_lazy as _

from orders.models import Order, OrderItem, OrderTax, OrderStatusHistory
from orders.serializers import (
    OrderSerializer, CreateOrderSerializer, OrderItemSerializer,
    OrderTaxSerializer, OrderStatusHistorySerializer
)
from orders.enums import OrderStatuses
from orders.filters import OrderFilter, OrderItemFilter, OrderStatusHistoryFilter, OrderTaxFilter
from common.permissions import IsOwnerOrStaff, IsStaffOrReadOnly


class OrderViewSet(SoftDeleteMixin, ModelViewSet):
    """
    ViewSet for managing orders with advanced filtering and searching.
    
    ### Search
    - Use `search` parameter to search by order number, user email, or username
    
    ### Filtering
    - `status`: Filter by order status (pending, paid, shipped, etc.)
    - `created_after`/`created_before`: Filter by date range (YYYY-MM-DD)
    - `min_total`/`max_total`: Filter by order total amount
    - `user`: Filter by user ID
    - `shipping_address__city`: Filter by shipping city
    - `shipping_address__country`: Filter by shipping country
    
    ### Ordering
    - Use `ordering` parameter with fields like `-date_created`, `total_amount`, etc.
    """
    queryset = Order.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrderFilter
    search_fields = [
        'order_number',
        'user__email',
        'user__username',
        'shipping_address__first_name',
        'shipping_address__last_name',
    ]
    ordering_fields = [
        'date_created', 
        'date_updated', 
        'total_amount',
        'status',
    ]
    ordering = ['-date_created']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateOrderSerializer
        return OrderSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # For non-staff users, only show their own orders
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
            
        return queryset.prefetch_related('items', 'taxes', 'status_history')
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order."""
        order = self.get_object()
        
        if not order.can_be_cancelled():
            return Response(
                {"detail": _("This order cannot be cancelled.")},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        order.cancel()
        return Response({"status": _("Order cancelled")})
    
    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def mark_paid(self, request, pk=None):
        """Mark an order as paid (admin only)."""
        order = self.get_object()
        order.mark_paid()
        return Response({"status": _("Order marked as paid")})

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def mark_completed(self, request, pk=None):
        """Mark an order as completed (admin only)."""
        order = self.get_object()
        order.mark_completed()
        return Response({"status": _("Order marked as completed")})

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def mark_delivered(self, request, pk=None):
        """Mark an order as delivered (admin only)."""
        order = self.get_object()
        order.mark_delivered()
        return Response({"status": _("Order marked as delivered")})

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def mark_refunded(self, request, pk=None):
        """Mark an order as refunded (admin only)."""
        order = self.get_object()
        order.mark_refunded()
        return Response({"status": _("Order marked as refunded")})

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def mark_unpaid(self, request, pk=None):
        """Mark an order as unpaid (admin only)."""
        order = self.get_object()
        order.mark_unpaid()
        return Response({"status": _("Order marked as unpaid")})

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def mark_approved(self, request, pk=None):
        """Mark an order as approved (admin only)."""
        order = self.get_object()
        order.mark_approved()
        return Response({"status": _("Order marked as approved")})

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def mark_processing(self, request, pk=None):
        """Mark an order as processing (admin only)."""
        order = self.get_object()
        order.mark_processing()
        return Response({"status": _("Order marked as processing")})

    @action(detail=True, methods=['post'], permission_classes=[IsStaffOrReadOnly])
    def mark_shipped(self, request, pk=None):
        """Mark an order as shipped (admin only)."""
        order = self.get_object()
        order.mark_shipped()
        return Response({"status": _("Order marked as shipped")})

    @action(detail=True, methods=['get'])
    def status_history(self, request, pk=None):
        """Get status history for an order."""
        order = self.get_object()
        history = order.status_history.all().order_by('-date_created')
        serializer = OrderStatusHistorySerializer(history, many=True)
        return Response(serializer.data)


class OrderItemViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing order items with filtering.
    
    ### Filtering
    - `order`: Filter by order ID
    - `product`: Filter by product ID
    - `variant`: Filter by variant ID
    - `quantity`: Filter by quantity (exact, gt, lt)
    - `total_price`: Filter by total price (exact, gt, lt)
    """
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = OrderItemFilter
    ordering_fields = ['date_created', 'total_price', 'quantity']
    ordering = ['-date_created']
    
    def get_queryset(self):
        queryset = OrderItem.objects.all()
            
        # For non-staff users, only show their own order items
        if not self.request.user.is_staff:
            queryset = queryset.filter(order__user=self.request.user)
            
        return queryset.select_related('product', 'variant', 'order')


class OrderTaxViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing order taxes.
    """
    serializer_class = OrderTaxSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = OrderTaxFilter
    ordering_fields = ['date_created', 'rate']
    ordering = ['-date_created', 'rate']

    def get_queryset(self):
        queryset = OrderTax.objects.all()
        
        order_id = self.request.query_params.get('order')
        if order_id:
            queryset = queryset.filter(order_id=order_id)
            
        # For non-staff users, only show their own order taxes
        if not self.request.user.is_staff:
            queryset = queryset.filter(order__user=self.request.user)
            
        return queryset


class OrderStatusHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing order status history with filtering.
    
    ### Filtering
    - `order`: Filter by order ID
    - `status`: Filter by status
    - `changed_by`: Filter by user ID who changed the status
    - `date_created`: Filter by date range (exact, gt, lt, gte, lte)
    """
    serializer_class = OrderStatusHistorySerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = OrderStatusHistoryFilter
    ordering_fields = ['date_created', 'status']
    ordering = ['-date_created']
    
    def get_queryset(self):
        queryset = OrderStatusHistory.objects.all()
            
        # For non-staff users, only show their own order history
        if not self.request.user.is_staff:
            queryset = queryset.filter(order__user=self.request.user)
            
        return queryset.select_related('order', 'changed_by')


class AdminOrderViewSet(SoftDeleteMixin, ModelViewSet):
    """
    Admin-only ViewSet for managing all orders with advanced filtering and searching.
    
    Inherits all filtering and searching from OrderViewSet but allows access to all orders.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrderFilter
    search_fields = [
        'order_number',
        'user__email',
        'user__username',
        'shipping_address__first_name',
        'shipping_address__last_name',
    ]
    ordering_fields = [
        'date_created', 
        'date_updated', 
        'total_amount',
        'status',
    ]
    ordering = ['-date_created']
    
    def get_queryset(self):
        return Order.objects.all().prefetch_related('items', 'taxes', 'status_history')
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status (admin only)."""
        order = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        
        if not new_status or new_status not in dict(OrderStatuses.choices):
            return Response(
                {"status": [_("Invalid status")]},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        order.status = new_status
        order.save()
        
        # Create status history record
        OrderStatusHistory.objects.create(
            order=order,
            status=new_status,
            notes=notes,
            changed_by=request.user
        )
        
        return Response({"status": _("Order status updated")})
