from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from .models import Category


class RecursiveField(serializers.Serializer):
    """"
    Handles recursive serialization of category children.
    """
    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data


class CategoryListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for category listings.
    Includes basic category information and child count.
    """
    children_count = serializers.IntegerField(
        source='children.count',
        read_only=True,
        help_text=_("Number of direct child categories")
    )
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'parent', 'description',
            'is_active', 'children_count', 'date_created', 'date_updated'
        ]
        read_only_fields = ['date_created', 'date_updated']


class CategoryDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for individual category view.
    Includes nested children and additional metadata.
    """
    children = RecursiveField(many=True, read_only=True)
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False,
        allow_null=True,
        help_text=_("Parent category ID (for subcategories)")
    )
    parent_name = serializers.StringRelatedField(
        source='parent',
        read_only=True,
        help_text=_("Name of the parent category")
    )
    full_path = serializers.SerializerMethodField(
        help_text=_("Full hierarchical path of the category")
    )
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'parent',
            'parent_name', 'children', 'full_path', 'is_active',
            'date_created', 'date_updated'
        ]
        read_only_fields = ['date_created', 'date_updated']
    
    def get_full_path(self, obj):
        """
        Returns the full hierarchical path of the category.
        Example: "Parent > Child > Grandchild"
        """
        path = []
        current = obj
        while current:
            path.insert(0, current.name)
            current = current.parent
        return ' > '.join(path)
    
    def validate(self, data):
        """
        Validate that a category is not set as its own parent
        and that circular references are not created.
        """
        instance = self.instance
        parent = data.get('parent')
        
        if instance and parent:
            # Check for self-reference
            if instance == parent:
                raise serializers.ValidationError({
                    'parent': _("A category cannot be its own parent.")
                })
            
            # Check for circular references
            if instance.is_descendant_of(parent):
                raise serializers.ValidationError({
                    'parent': _("Cannot create circular reference in category hierarchy.")
                })
        
        return data


class CategoryTreeSerializer(serializers.ModelSerializer):
    """
    Serializer for hierarchical category tree.
    Optimized for building navigation menus and category trees.
    """
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'children']
    
    def get_children(self, obj):
        """
        Recursively get children for the category tree.
        Only includes active categories.
        """
        children = obj.children.filter(is_active=True, is_deleted=False)
        return CategoryTreeSerializer(children, many=True).data


class CategoryBulkCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a single category.
    Used as the child serializer for bulk operations.
    """
    class Meta:
        model = Category
        fields = ['name', 'description', 'parent', 'is_active']
        extra_kwargs = {
            'name': {'required': True},
            'description': {'required': False, 'allow_blank': True},
            'parent': {'required': False, 'allow_null': True},
            'is_active': {'required': False, 'default': True}
        }
    
    def validate(self, data):
        """Validate the category data."""
        # Add any custom validation here if needed
        return data


class CategoryBulkUpdateSerializer(serializers.Serializer):
    """
    Handles bulk updates for categories.
    """
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=100,
        help_text=_("List of category IDs to update")
    )
    is_active = serializers.BooleanField(
        required=False,
        help_text=_("Set active status for all selected categories")
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False,
        allow_null=True,
        help_text=_("Set parent category for all selected categories")
    )
    
    def validate_ids(self, value):
        """Validate that all category IDs exist."""
        existing_ids = set(Category.objects.filter(id__in=value).values_list('id', flat=True))
        invalid_ids = set(value) - existing_ids
        
        if invalid_ids:
            raise serializers.ValidationError(
                _("The following category IDs do not exist: {}".format(", ".join(map(str, invalid_ids)))
                  )
            )
        return value
    
    def validate(self, attrs):
        """Validate that parent is not in the list of IDs being updated."""
        if 'parent' in attrs and attrs['parent'] and attrs['parent'].id in attrs.get('ids', []):
            raise serializers.ValidationError({
                'parent': _("Cannot set a category as its own parent.")
            })
        return attrs
    
    def update(self, instance, validated_data):
        # This is a bulk update, so we don't use the instance parameter
        ids = validated_data.pop('ids')
        update_fields = {k: v for k, v in validated_data.items() if v is not None}
        
        if update_fields:
            # Update all categories in a single query
            Category.objects.filter(id__in=ids).update(**update_fields)
        
        return Category.objects.filter(id__in=ids)
