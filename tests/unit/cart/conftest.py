import pytest
from decimal import Decimal
from datetime import timedelta, datetime
from django.utils import timezone

from cart.models import Cart, CartItem, Coupon, SavedCart, SavedCartItem
from products.models import Product
from category.models import Category

from tests.conftest import authenticated_client, verified_user, client


@pytest.fixture
def category_factory(db):
    """Create a category factory fixture."""
    def _create_category(**kwargs):
        defaults = {
            'name': 'Test Category',
            'slug': 'test-category',
            'description': 'Test category description',
            'is_active': True
        }
        defaults.update(kwargs)
        return Category.objects.create(**defaults)
    return _create_category


@pytest.fixture
def product_factory(db, category_factory):
    """Create a product factory fixture."""
    def _create_product(**kwargs):
        # Get or create a default category if not provided
        if 'category' not in kwargs:
            kwargs['category'] = category_factory()
            
        defaults = {
            'name': 'Test Product',
            'slug': 'test-product',
            'price': Decimal('19.99'),
            'stock_quantity': 100,
            'is_active': True,
            'description': 'Test description',
            'sku': 'TEST123',
            'weight': Decimal('1.0'),
            'length': Decimal('10.0'),
            'width': Decimal('10.0'),
            'height': Decimal('10.0'),
        }
        defaults.update(kwargs)
        return Product.objects.create(**defaults)
    return _create_product


@pytest.fixture
def cart_factory(db, user_factory):
    """Create a cart factory fixture."""
    def _create_cart(**kwargs):
        if 'user' not in kwargs:
            kwargs['user'] = user_factory()
            
        defaults = {
            'status': 'active',
            'shipping_address': None,
            'billing_address': None,
            'shipping_method': 'standard',
            'shipping_cost': Decimal('0.00'),
            'notes': '',
        }
        defaults.update(kwargs)
        return Cart.objects.create(**defaults)
    return _create_cart


@pytest.fixture
def cart_item_factory(db, cart_factory, product_factory):
    """Create a cart item factory fixture."""
    def _create_cart_item(**kwargs):
        if 'cart' not in kwargs:
            kwargs['cart'] = cart_factory()
        if 'product' not in kwargs:
            kwargs['product'] = product_factory()
            
        defaults = {
            'quantity': 1,
            'price': kwargs['product'].price,
            'notes': '',
        }
        defaults.update(kwargs)
        return CartItem.objects.create(**defaults)
    return _create_cart_item


@pytest.fixture
def coupon_factory(db, product_factory):
    """Create a coupon factory fixture."""
    def _create_coupon(**kwargs):
        if 'product' not in kwargs:
            kwargs['product'] = product_factory()
            
        defaults = {
            'coupon_code': 'TEST10',
            'discount_type': 'percentage',
            'discount_amount': Decimal('10.00'),
            'minimum_order_amount': Decimal('50.00'),
            'maximum_discount_amount': None,
            'start_date': timezone.now() - timedelta(days=1),
            'end_date': timezone.now() + timedelta(days=30),
            'is_active': True,
            'usage_limit': 100,
            'used_count': 0,
            'description': 'Test coupon',
        }
        defaults.update(kwargs)
        return Coupon.objects.create(**defaults)
    return _create_coupon


@pytest.fixture
def saved_cart_factory(db, user_factory):
    """Create a saved cart factory fixture."""
    def _create_saved_cart(**kwargs):
        if 'user' not in kwargs:
            kwargs['user'] = user_factory()
            
        defaults = {
            'name': 'Saved Cart',
            'is_default': False,
            'notes': 'Test saved cart',
        }
        defaults.update(kwargs)
        return SavedCart.objects.create(**defaults)
    return _create_saved_cart


@pytest.fixture
def saved_cart_item_factory(db, saved_cart_factory, product_factory):
    """Create a saved cart item factory fixture."""
    def _create_saved_cart_item(**kwargs):
        if 'saved_cart' not in kwargs:
            kwargs['saved_cart'] = saved_cart_factory()
        if 'product' not in kwargs:
            kwargs['product'] = product_factory()
            
        defaults = {
            'quantity': 1,
            'price': kwargs['product'].price,
            'product_snapshot': {
                'id': kwargs['product'].id,
                'name': kwargs['product'].name,
                'price': str(kwargs['product'].price),
                'sku': kwargs['product'].sku,
            },
            'notes': '',
        }
        defaults.update(kwargs)
        return SavedCartItem.objects.create(**defaults)
    return _create_saved_cart_item


