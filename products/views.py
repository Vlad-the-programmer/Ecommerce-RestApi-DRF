from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django_filters.rest_framework import DjangoFilterBackend

from .models import Product, ProductVariant, ProductImage, Location
from .serializers import (
    ProductListSerializer, ProductDetailSerializer, ProductCreateUpdateSerializer,
    ProductBulkUpdateSerializer, ProductVariantSerializer, ProductImageSerializer,
    LocationSerializer, DigitalProductSerializer, ServiceProductSerializer
)
from .filters import ProductFilter


class LocationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing product locations.
    """
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'city', 'country']
    ordering_fields = ['name', 'city', 'country']
    ordering = ['name']


class ProductViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing products.
    """
    queryset = Product.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['product_name', 'sku', 'barcode']
    ordering_fields = ['price', 'date_created', 'date_updated']
    ordering = ['-date_created']

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser, IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        """
        Return appropriate serializer class based on action.
        """
        if self.action == 'list':
            return ProductListSerializer
        elif self.action == 'retrieve':
            return ProductDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        elif self.action == 'bulk_update':
            return ProductBulkUpdateSerializer
        elif self.action == 'digital_products':
            return DigitalProductSerializer
        elif self.action == 'service_products':
            return ServiceProductSerializer
        return ProductListSerializer

    def get_queryset(self):
        """
        Return different querysets based on user permissions.
        """
        if self.request.user.is_staff:
            return Product.admin.all()
        return Product.objects.published()

    @action(detail=False, methods=['post'])
    def bulk_update(self, request, *args, **kwargs):
        """
        Bulk update multiple products.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated_products = serializer.save()
        return Response(
            {"message": f"Successfully updated {len(updated_products)} products"},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'])
    def digital_products(self, request):
        """
        Get all digital products.
        """
        digital_products = self.get_queryset().filter(product_type='DIGITAL')
        page = self.paginate_queryset(digital_products)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(digital_products, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def service_products(self, request):
        """
        Get all service products.
        """
        service_products = self.get_queryset().filter(product_type='SERVICE')
        page = self.paginate_queryset(service_products)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(service_products, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def variants(self, request, pk=None):
        """
        Get all variants for a specific product.
        """
        product = self.get_object()
        variants = product.product_variants.all()
        serializer = ProductVariantSerializer(variants, many=True)
        return Response(serializer.data)


class ProductVariantViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing product variants.
    """
    queryset = ProductVariant.objects.all()
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['sku', 'barcode']
    ordering_fields = ['price_adjustment', 'stock_quantity']
    ordering = ['sku']

    def get_queryset(self):
        """
        Optionally filter by product ID if provided in the URL.
        """
        queryset = super().get_queryset()
        product_id = self.request.query_params.get('product_id')
        if product_id is not None:
            queryset = queryset.filter(product_id=product_id)
        return queryset


class ProductImageViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing product images.
    """
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        """
        Optionally filter by product ID if provided in the URL.
        """
        queryset = super().get_queryset()
        product_id = self.request.query_params.get('product_id')
        if product_id is not None:
            queryset = queryset.filter(product_id=product_id)
        return queryset

    def perform_create(self, serializer):
        """
        Set the product when creating a new image.
        """
        product_id = self.request.data.get('product')
        if product_id:
            serializer.save(product_id=product_id)
        else:
            serializer.save()
