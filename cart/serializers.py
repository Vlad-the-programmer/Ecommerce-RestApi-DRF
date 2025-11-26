from rest_framework import serializers
from django.utils import timezone

from products.models import Product
from products.serializers import ProductDetailSerializer
from .models import Cart, CartItem, Coupon, SavedCart, SavedCartItem


class ApplyCouponSerializer(serializers.Serializer):
    """Serializer for applying a coupon to a cart."""
    coupon_code = serializers.CharField(max_length=10, required=True)


class CartItemSerializer(serializers.ModelSerializer):
    """Serializer for cart items."""
    product = ProductDetailSerializer(read_only=True)
    cart_id = serializers.UUIDField(
        read_only=True,
        source='cart__id'
    )
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True, is_deleted=False),
        write_only=True,
        source='product'
    )
    total_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_id', 'cart_id', 'quantity',
            'total_price', 'date_created', 'date_updated'
        ]
        read_only_fields = ['date_created', 'cart_id', 'date_updated']

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value


class CartSerializer(serializers.ModelSerializer):
    """Serializer for shopping carts."""
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    total_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        read_only=True
    )
    discount_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    final_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    coupon_code = serializers.CharField(
        source='coupon.coupon_code',
        read_only=True
    )

    class Meta:
        model = Cart
        fields = [
            'id', 'user', 'status', 'items', 'total_items', 'total_price',
            'coupon', 'coupon_code', 'discount_amount', 'final_price',
            'date_created', 'date_updated'
        ]
        read_only_fields = [
            'user', 'status', 'total_items', 'total_price', 'discount_amount',
            'final_price', 'date_created', 'date_updated'
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['total_items'] = instance.total_items
        representation['total_price'] = instance.total_price
        representation['discount_amount'] = instance.discount_amount
        representation['final_price'] = instance.final_price
        return representation


class CouponSerializer(serializers.ModelSerializer):
    """Serializer for coupons."""
    is_valid = serializers.BooleanField(read_only=True)
    product = ProductDetailSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True, is_deleted=False),
        write_only=True,
        source='product'
    )

    class Meta:
        model = Coupon
        fields = [
            'id', 'coupon_code', 'discount_amount', 'minimum_cart_amount',
            'expiration_date', 'usage_limit', 'used_count', 'is_expired',
            'is_valid', 'product', 'product_id', 'date_created', 'date_updated'
        ]
        read_only_fields = ['is_expired', 'used_count', 'date_created', 'date_updated']

    def validate(self, attrs):
        if 'expiration_date' in attrs and attrs['expiration_date'] <= timezone.now():
            raise serializers.ValidationError({
                'expiration_date': 'Expiration date must be in the future.'
            })
        
        if 'discount_amount' in attrs and not (0 < attrs['discount_amount'] <= 100):
            raise serializers.ValidationError({
                'discount_amount': 'Discount amount must be between 1 and 100.'
            })
        
        return attrs


class SavedCartItemSerializer(serializers.ModelSerializer):
    """Serializer for saved cart items."""
    product = ProductDetailSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True, is_deleted=False),
        write_only=True,
        source='product'
    )
    total_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = SavedCartItem
        fields = [
            'id', 'product', 'product_id', 'quantity', 'price', 
            'total_price', 'product_snapshot', 'date_created', 'date_updated'
        ]
        read_only_fields = ['product_snapshot', 'date_created', 'date_updated']

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value


class SavedCartSerializer(serializers.ModelSerializer):
    """Serializer for saved carts."""
    items = SavedCartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    total_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = SavedCart
        fields = [
            'id', 'user', 'name', 'description', 'is_default',
            'expires_at', 'items', 'total_items', 'total_price',
            'date_created', 'date_updated'
        ]
        read_only_fields = ['user', 'date_created', 'date_updated']

    def validate(self, attrs):
        # If this is a new cart or is_default is being set to True
        if (self.instance is None or attrs.get('is_default', False)) and 'user' in self.context:
            # If this is a new cart and is_default is True, or if we're updating an existing cart to be default
            if attrs.get('is_default', False):
                # Unset any other default carts for this user
                # Get the queryset of carts to update
                carts_to_update = SavedCart.objects.filter(
                    user=self.context['user'],
                    is_default=True
                ).exclude(pk=self.instance.pk if self.instance else None)

                for cart in carts_to_update:
                    cart.is_default = False

                if carts_to_update.exists():
                    SavedCart.objects.bulk_update(carts_to_update, fields=['is_default'])

        return attrs
    
    def create(self, validated_data):
        # Set the user from the request
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['total_items'] = instance.items.count()
        representation['total_price'] = sum(
            item.quantity * item.price 
            for item in instance.items.all()
        )
        return representation
