from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _
from django.db.models import Avg, Count, Q

from common.permissions import IsAdminOrOwner
from .models import Review
from .serializers import (
    ReviewCreateSerializer,
    ReviewUpdateSerializer,
    ReviewListSerializer
)


class ReviewViewSet(SoftDeleteMixin, ModelViewSet):
    """
    API endpoint that allows reviews to be viewed or edited.
    """
    queryset = Review.objects.all()
    serializer_class = ReviewListSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsAdminOrOwner]

    def get_serializer_class(self):
        if self.action == 'create':
            return ReviewCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ReviewUpdateSerializer
        return ReviewListSerializer

    def get_queryset(self):
        """
        Optionally filter by product or user
        """
        queryset = super().get_queryset()

        product_id = self.request.query_params.get('product_id')
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        user_id = self.request.query_params.get('user_id')
        if user_id and self.request.user.is_staff:
            queryset = queryset.filter(user_id=user_id)

        return queryset.select_related('user', 'product')

    def perform_create(self, serializer):
        """Set the user to the current user when creating a review."""
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get review statistics for a product."""
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response(
                {"error": _("product_id parameter is required")},
                status=status.HTTP_400_BAD_REQUEST
            )

        stats = Review.objects.filter(
            product_id=product_id,
        ).aggregate(
            average_rating=Avg('rating'),
            total_reviews=Count('id'),
            five_star=Count('id', filter=Q(rating=5)),
            four_star=Count('id', filter=Q(rating=4)),
            three_star=Count('id', filter=Q(rating=3)),
            two_star=Count('id', filter=Q(rating=2)),
            one_star=Count('id', filter=Q(rating=1))
        )

        return Response(stats)