from rest_framework import status, permissions
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from common.permissions import IsAdminOrReadOnly
from .models import Category
from .serializers import (
    CategoryListSerializer,
    CategoryDetailSerializer,
    CategoryTreeSerializer,
    CategoryBulkCreateSerializer,
    CategoryBulkUpdateSerializer
)


class CategoryViewSet(ModelViewSet):
    """
    API endpoint that allows categories to be viewed or edited.
    """
    queryset = Category.objects.all()
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'

    def get_serializer_class(self):
        """
        Return appropriate serializer class based on action.
        """
        if self.action == 'list':
            return CategoryListSerializer
        elif self.action == 'retrieve':
            return CategoryDetailSerializer
        elif self.action == 'tree':
            return CategoryTreeSerializer
        elif self.action == 'bulk_create':
            return CategoryBulkCreateSerializer
        elif self.action == 'bulk_update':
            return CategoryBulkUpdateSerializer
        return CategoryDetailSerializer

    def get_queryset(self):
        """
        Optionally filter by parent category or return root categories.
        """
        queryset = super().get_queryset()
        parent_slug = self.request.query_params.get('parent', None)
        
        if parent_slug == 'root' or parent_slug == '':
            return Category.objects.root_categories()
        elif parent_slug:
            parent = Category.objects.by_slug(parent_slug)
            if parent:
                return Category.objects.children_of(parent)
        
        return queryset

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """
        Get category tree structure.
        """
        root_categories = Category.objects.root_categories()
        serializer = self.get_serializer(root_categories, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def children(self, request, slug=None):
        """
        Get direct children of a category.
        """
        category = self.get_object()
        children = Category.objects.children_of(category)
        page = self.paginate_queryset(children)
        if page is not None:
            serializer = CategoryListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = CategoryListSerializer(children, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """
        Bulk create categories.
        Expected payload format:
        {
            "categories": [
                {"name": "Category 1", "description": "Desc 1"},
                {"name": "Category 2", "parent": 1, "is_active": true}
            ]
        }
        """
        if not isinstance(request.data.get('categories'), list):
            return Response(
                {'error': 'Expected a list of categories in the "categories" field'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        serializer = CategoryBulkCreateSerializer(
            data=request.data['categories'], 
            many=True,
            context=self.get_serializer_context()
        )
        
        serializer.is_valid(raise_exception=True)
        try:
            categories = serializer.save()
            return Response(
                CategoryListSerializer(categories, many=True).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    @action(detail=False, methods=['put', 'patch'])
    def bulk_update(self, request):
        """
        Bulk update categories.
        Expected payload format:
        {
            "ids": [1, 2, 3],
            "is_active": false
        }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            # Get the update data (all fields except 'ids')
            update_data = {
                k: v for k, v in serializer.validated_data.items()
                if k != 'ids'
            }

            if not update_data:
                return Response(
                    {'error': 'No fields to update'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update the categories
            updated_count = Category.objects.filter(
                id__in=serializer.validated_data['ids']
            ).update(**update_data)

            return Response({
                'updated_count': updated_count,
                'detail': f'Successfully updated {updated_count} categories.'
            }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def perform_destroy(self, instance):
        """
        Soft delete the category instance.
        """
        can_delete, reason = instance.can_be_deleted()
        if not can_delete:
            raise serializers.ValidationError(reason)
        instance.delete()
