from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from common.mixins import SoftDeleteMixin
from .models import Refund
from .notifier import notify_by_email, RefundNotifier
from .serializers import RefundSerializer, RefundCreateSerializer, RefundUpdateSerializer
from .enums import RefundStatus
from common.permissions import IsOwnerOrStaff


class RefundViewSet(SoftDeleteMixin, ModelViewSet):
    """
    API endpoint that allows refunds to be viewed or edited.
    """
    queryset = Refund.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]

    def get_serializer_class(self):
        if self.action == 'create':
            return RefundCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return RefundUpdateSerializer
        return RefundSerializer

    def get_queryset(self):
        """
        Filter refunds to only show the current user's refunds unless they're staff.
        """
        queryset = super().get_queryset()
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
            return queryset
        return queryset.select_related(
            'user', 'order', 'payment'
        ).prefetch_related('items')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a refund request."""
        refund = self.get_object()
        if refund.status != RefundStatus.PENDING:
            return Response(
                {'detail': 'Only pending refunds can be approved.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        refund.approve(processed_by=request.user)
        notify_by_email(notification_type=RefundStatus.APPROVED, notifier=RefundNotifier(refund))

        serializer = self.get_serializer(refund)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a refund request."""
        refund = self.get_object()
        reason = request.data.get('reason', '')

        if not reason:
            return Response(
                {'reason': 'Reason is required for rejection.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        refund.reject(reason=reason, rejected_by=request.user)

        notify_by_email(notification_type=RefundStatus.REJECTED, notifier=RefundNotifier(refund))

        serializer = self.get_serializer(refund)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a refund request."""
        refund = self.get_object()

        refund.cancel(cancelled_by=request.user)

        notify_by_email(notification_type=RefundStatus.CANCELLED, notifier=RefundNotifier(refund))

        serializer = self.get_serializer(refund)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def complete(self, request, pk=None):
        """Complete a refund request."""
        refund = self.get_object()

        refund.complete(completed_by=request.user)
        notify_by_email(notification_type=RefundStatus.COMPLETED, notifier=RefundNotifier(refund))

        serializer = self.get_serializer(refund)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Set the user to the current user when creating a refund."""
        serializer.save(user=self.request.user)
