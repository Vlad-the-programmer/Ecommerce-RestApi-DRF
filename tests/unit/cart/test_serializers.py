import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from rest_framework.exceptions import ValidationError

from cart.serializers import (
    ApplyCouponSerializer,
    CartItemSerializer,
    CartSerializer,
    CouponSerializer,
    SavedCartSerializer,
    SavedCartItemSerializer
)


class TestApplyCouponSerializer:
    """Test cases for the ApplyCouponSerializer."""
    
    def test_valid_coupon_application(self, coupon_factory):
        """Test applying a valid coupon."""
        coupon = coupon_factory(coupon_code="TEST10")
        
        data = {'coupon_code': 'TEST10'}
        serializer = ApplyCouponSerializer(data=data)
        
        assert serializer.is_valid() is True
        assert serializer.validated_data['coupon_code'] == 'TEST10'
        assert serializer.validated_data['coupon'] == coupon

    def test_invalid_coupon_application(self):
        """Test applying a non-existent coupon."""
        data = {'coupon_code': 'INVALID'}
        serializer = ApplyCouponSerializer(data=data)
        
        assert serializer.is_valid() is False
        assert 'coupon_code' in serializer.errors
        assert 'not found' in str(serializer.errors['coupon_code'][0])

    def test_expired_coupon_application(self, coupon_factory):
        """Test applying an expired coupon."""
        coupon = coupon_factory(
            coupon_code="EXPIRED",
            expiration_date='2000-01-01T00:00:00Z'
        )
        
        data = {'coupon_code': 'EXPIRED'}
        serializer = ApplyCouponSerializer(data=data)
        
        assert serializer.is_valid() is False
        assert 'coupon_code' in serializer.errors
        assert 'expired' in str(serializer.errors['coupon_code'][0]).lower()


class TestCartItemSerializer:
    """Test cases for the CartItemSerializer."""
    
    def test_serialize_cart_item(self, cart_item_factory):
        """Test serializing a cart item."""
        cart_item = cart_item_factory(quantity=2, price=Decimal('19.99'))
        serializer = CartItemSerializer(cart_item)
        
        assert serializer.data['id'] == cart_item.id
        assert serializer.data['quantity'] == 2
        assert Decimal(serializer.data['price']) == Decimal('19.99')
        assert 'product' in serializer.data
        assert 'subtotal' in serializer.data
        assert Decimal(serializer.data['subtotal']) == Decimal('39.98')  # 19.99 * 2

    def test_create_cart_item(self, product_factory, authenticated_client):
        """Test creating a new cart item through the serializer."""
        product = product_factory(price=Decimal('25.00'))
        request = MagicMock()
        request.user = authenticated_client.user
        
        data = {
            'product_id': product.id,
            'quantity': 2
        }
        
        serializer = CartItemSerializer(
            data=data,
            context={'request': request}
        )
        
        assert serializer.is_valid() is True
        cart_item = serializer.save()
        
        assert cart_item.product == product
        assert cart_item.quantity == 2
        assert cart_item.price == product.price
        assert cart_item.cart.user == request.user

    def test_validate_quantity_negative(self, product_factory):
        """Test validation of negative quantity."""
        product = product_factory()
        data = {
            'product_id': product.id,
            'quantity': -1
        }
        
        serializer = CartItemSerializer(data=data)
        
        assert serializer.is_valid() is False
        assert 'quantity' in serializer.errors


class TestCartSerializer:
    """Test cases for the CartSerializer."""
    
    def test_serialize_cart(self, cart_item_factory):
        """Test serializing a cart with items."""
        cart_item1 = cart_item_factory(quantity=2, price=Decimal('10.00'))
        cart_item2 = cart_item_factory(cart=cart_item1.cart, quantity=1, price=Decimal('20.00'))
        
        serializer = CartSerializer(cart_item1.cart)
        
        assert len(serializer.data['items']) == 2
        assert Decimal(serializer.data['total']) == Decimal('40.00')
        assert 'coupon' in serializer.data
        assert 'items_count' in serializer.data
        assert serializer.data['items_count'] == 3  # 2 + 1 items


class TestCouponSerializer:
    """Test cases for the CouponSerializer."""
    
    def test_serialize_coupon(self, coupon_factory):
        """Test serializing a coupon."""
        coupon = coupon_factory(
            coupon_code="SERIALIZER",
            discount_amount=15,
            minimum_amount=100
        )
        
        serializer = CouponSerializer(coupon)
        
        assert serializer.data['coupon_code'] == 'SERIALIZER'
        assert serializer.data['discount_amount'] == 15
        assert serializer.data['is_valid'] is True
        assert 'product' in serializer.data

    def test_validate_coupon_code_unique(self, coupon_factory):
        """Test validation of unique coupon code."""
        coupon_factory(coupon_code="DUPLICATE")
        
        data = {
            'coupon_code': 'DUPLICATE',
            'discount_amount': 10,
            'minimum_amount': 50
        }
        
        serializer = CouponSerializer(data=data)
        
        assert serializer.is_valid() is False
        assert 'coupon_code' in serializer.errors


class TestSavedCartSerializer:
    """Test cases for the SavedCartSerializer."""
    
    def test_serialize_saved_cart(self, saved_cart_factory):
        """Test serializing a saved cart."""
        saved_cart = saved_cart_factory(name="Test Cart")
        serializer = SavedCartSerializer(saved_cart)
        
        assert serializer.data['name'] == 'Test Cart'
        assert 'items' in serializer.data
        assert 'user' in serializer.data
        assert 'date_created' in serializer.data

    def test_create_saved_cart(self, cart_item_factory, authenticated_client):
        """Test creating a saved cart from current cart."""
        cart_item = cart_item_factory(cart__user=authenticated_client.user)
        
        data = {
            'name': 'My Saved Cart',
            'description': 'Test description'
        }
        
        serializer = SavedCartSerializer(
            data=data,
            context={'request': MagicMock(user=authenticated_client.user)}
        )
        
        assert serializer.is_valid() is True
        saved_cart = serializer.save()
        
        assert saved_cart.user == authenticated_client.user
        assert saved_cart.name == 'My Saved Cart'
        assert saved_cart.items.count() == 1


class TestSavedCartItemSerializer:
    """Test cases for the SavedCartItemSerializer."""
    
    def test_serialize_saved_cart_item(self, saved_cart_item_factory):
        """Test serializing a saved cart item."""
        saved_cart_item = saved_cart_item_factory(
            quantity=2, 
            price=Decimal('19.99'),
            product_snapshot={'name': 'Test Product'}
        )
        
        serializer = SavedCartItemSerializer(saved_cart_item)
        
        assert serializer.data['quantity'] == 2
        assert Decimal(serializer.data['price']) == Decimal('19.99')
        assert 'product' in serializer.data
        assert 'product_snapshot' in serializer.data
        assert serializer.data['product_snapshot']['name'] == 'Test Product'
