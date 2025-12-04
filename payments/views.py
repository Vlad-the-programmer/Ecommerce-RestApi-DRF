from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

from common.permissions import IsAdminOrReadOnly
from payments.models import Payment
from payments.serializers import (
    PaymentSerializer,
    PaymentCreateSerializer,
    PaymentUpdateSerializer,
)
from payments.enums import PaymentStatus


class PaymentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows payments to be viewed or edited.
    """
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = {
        'status': ['exact', 'in'],
        'method': ['exact', 'in'],
        'amount': ['exact', 'gt', 'lt', 'gte', 'lte'],
        'transaction_date': ['date', 'date__gt', 'date__lt', 'date__gte', 'date__lte'],
        'user': ['exact'],
        'invoice': ['exact'],
    }
    ordering_fields = ['transaction_date', 'amount', 'created_at', 'updated_at']
    search_fields = ['payment_reference', 'notes', 'invoice__invoice_number']

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PaymentUpdateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        Regular users can only see their own payments.
        Staff users can see all payments.
        """
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    def perform_create(self, serializer):
        """"
        Automatically set the user to the current user when creating a payment.
        """
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_as_completed(self, request, pk=None):
        """
        Custom action to mark a payment as completed.
        """
        payment = self.get_object()
        if payment.status == PaymentStatus.COMPLETED:
            return Response(
                {'status': 'Payment is already marked as completed'},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment.status = PaymentStatus.COMPLETED
        payment.confirmed_at = timezone.now()
        payment.save(update_fields=['status', 'confirmed_at', 'updated_at'])

        # Here add additional logic like sending notifications
        # or triggering other business logic

        return Response({'status': 'Payment marked as completed'})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """"
        Get summary statistics for payments.
        """
        queryset = self.filter_queryset(self.get_queryset())

        total_payments = queryset.count()
        total_amount = queryset.aggregate(total=Sum('amount'))['total'] or 0

        status_summary = queryset.values('status').annotate(
            count=Count('id'),
            amount=Sum('amount')
        )

        method_summary = queryset.values('method').annotate(
            count=Count('id'),
            amount=Sum('amount')
        )

        return Response({
            'total_payments': total_payments,
            'total_amount': total_amount,
            'by_status': status_summary,
            'by_method': method_summary,
        })
