from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from wishlist.models import Wishlist, WishListItem, WishListItemPriority
from products.serializers import ProductDetailSerializer, ProductVariantSerializer
from users.serializers import UserDetailsSerializer


class WishlistItemSerializer(serializers.ModelSerializer):
    """Serializer for wishlist items."""
    product = ProductDetailSerializer(read_only=True)
    variant = ProductVariantSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True, required=True)
    variant_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    priority_display = serializers.ChoiceField(
        source='get_priority_display', 
        read_only=True,
        label=_("Priority Display")
    )

    class Meta:
        model = WishListItem
        fields = [
            'id', 'wishlist', 'product', 'variant', 'product_id', 'variant_id',
            'quantity', 'note', 'priority', 'priority_display', 'date_created', 'date_updated'
        ]
        read_only_fields = ['id', 'wishlist', 'date_created', 'date_updated']
        extra_kwargs = {
            'quantity': {'min_value': 1, 'default': 1},
            'priority': {'default': WishListItemPriority.MEDIUM},
        }

    def validate(self, attrs):
        from products.models import Product
        try:
            product = Product.objects.get(pk=attrs['product_id'], is_active=True, is_deleted=False)
            attrs['product'] = product
        except Product.DoesNotExist:
            raise ValidationError({"product_id": _("Product not found or inactive")})

        if attrs.get('variant_id'):
            from products.models import ProductVariant
            try:
                variant = product.variants.get(
                    pk=attrs['variant_id'],
                )
                attrs['variant'] = variant
            except ProductVariant.DoesNotExist:
                raise ValidationError({
                    "variant_id": _("Variant not found, inactive, or doesn't belong to this product")
                })

        return attrs

    def create(self, validated_data):
        validated_data.pop('product_id', None)
        validated_data.pop('variant_id', None)
        return super().create(validated_data)


class WishlistSerializer(serializers.ModelSerializer):
    """Serializer for wishlists."""
    user = UserDetailsSerializer(read_only=True)
    items = WishlistItemSerializer(many=True, read_only=True, source='wishlist_items')
    items_count = serializers.IntegerField(read_only=True, source='items_count')

    class Meta:
        model = Wishlist
        fields = [
            'id', 'user', 'name', 'is_public', 'items_count', 'items',
            'date_created', 'date_updated', 'is_deleted'
        ]
        read_only_fields = ['id', 'user', 'date_created', 'date_updated', 'is_deleted', 'items_count']

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(_("Wishlist name cannot be empty"))
        return value.strip()

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            validated_data['user'] = request.user
        
        if not validated_data.get('name'):
            validated_data['name'] = _("My Wishlist")
            
        return super().create(validated_data)


class WishlistItemCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for creating wishlist items."""
    product_id = serializers.IntegerField(required=True)
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    priority = serializers.ChoiceField(
        choices=WishListItemPriority.choices,
        default=WishListItemPriority.MEDIUM
    )

    class Meta:
        model = WishListItem
        fields = ['product_id', 'variant_id', 'quantity', 'note', 'priority']


class WishlistItemUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating wishlist items."""
    quantity = serializers.IntegerField(min_value=1, required=False)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    priority = serializers.ChoiceField(choices=WishListItemPriority.choices, required=False)

    class Meta:
        model = WishListItem
        fields = ['quantity', 'note', 'priority']


class WishlistItemMoveToCartSerializer(serializers.Serializer):
    """Serializer for moving wishlist items to cart."""
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        help_text=_("List of wishlist item IDs to move to cart")
    )
    
    def validate_item_ids(self, value):
        if not value:
            raise serializers.ValidationError(_("At least one item ID is required"))
        return value
