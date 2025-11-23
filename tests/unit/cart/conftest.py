import pytest
from decimal import Decimal
from datetime import timedelta, datetime
from django.utils import timezone
from django.urls import reverse

from cart.models import Cart, CartItem, Coupon, SavedCart, SavedCartItem
from products.models import Product, Location
from category.models import Category


# URL Fixtures

@pytest.fixture
def cart_list_url():
    """URL for cart list endpoint."""
    return reverse('v1:cart-list')


@pytest.fixture
def cart_detail_url():
    """URL factory for cart detail endpoint."""
    def _cart_detail_url(cart_id):
        return reverse('v1:cart-detail', kwargs={'pk': cart_id})
    return _cart_detail_url


@pytest.fixture
def cart_apply_coupon_url():
    """URL factory for apply coupon endpoint."""
    def _cart_apply_coupon_url(cart_id):
        return reverse('v1:cart-apply-coupon', kwargs={'pk': cart_id})
    return _cart_apply_coupon_url


@pytest.fixture
def cart_checkout_url():
    """URL factory for cart checkout endpoint."""
    def _cart_checkout_url(cart_id):
        return reverse('v1:cart-checkout', kwargs={'pk': cart_id})
    return _cart_checkout_url


@pytest.fixture
def cart_item_list_url():
    """URL for cart item list endpoint."""
    return reverse('v1:cartitem-list')


@pytest.fixture
def cart_item_detail_url():
    """URL factory for cart item detail endpoint."""
    def _cart_item_detail_url(item_id):
        return reverse('v1:cartitem-detail', kwargs={'pk': item_id})
    return _cart_item_detail_url


@pytest.fixture
def coupon_list_url():
    """URL for coupon list endpoint."""
    return reverse('v1:coupon-list')


@pytest.fixture
def saved_cart_list_url():
    """URL for saved cart list endpoint."""
    return reverse('v1:savedcart-list')


@pytest.fixture
def saved_cart_detail_url():
    """URL factory for saved cart detail endpoint."""
    def _saved_cart_detail_url(cart_id):
        return reverse('v1:savedcart-detail', kwargs={'pk': cart_id})
    return _saved_cart_detail_url


@pytest.fixture
def saved_cart_restore_url():
    """URL factory for saved cart restore endpoint."""
    def _saved_cart_restore_url(cart_id):
        return reverse('v1:savedcart-restore', kwargs={'pk': cart_id})
    return _saved_cart_restore_url


# Model Factories

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
        # Create the category without using create() to avoid the force_insert issue
        category = Category(**defaults)
        category.save()
        return category
    return _create_category


@pytest.fixture
def location_factory(db):
    """Create a location factory fixture."""
    def _create_location(**kwargs):
        defaults = {
            'name': 'Test Location',
            'address_line1': '123 Test St',
            'city': 'Test City',
            'postal_code': '12345',
            'country': 'US',
            'is_active': True
        }
        defaults.update(kwargs)
        return Location.objects.create(**defaults)
    return _create_location


@pytest.fixture
def product_factory(db, category_factory, location_factory):
    """Create a product factory fixture."""
    def _create_product(**kwargs):
        from products.enums import ProductType, ProductCondition, ProductStatus, StockStatus, ProductLabel
        
        # Get or create required related objects if not provided
        if 'category' not in kwargs:
            kwargs['category'] = category_factory()
            
        # Handle product type specific fields
        product_type = kwargs.get('product_type', ProductType.PHYSICAL)
        
        defaults = {
            'product_name': 'Test Product',
            'product_type': product_type,
            'price': Decimal('19.99'),
            'compare_at_price': Decimal('29.99'),
            'product_description': 'Test product description',
            'condition': ProductCondition.NEW,
            'status': ProductStatus.PUBLISHED,
            'stock_status': StockStatus.IN_STOCK,
            'label': ProductLabel.NONE,
            'low_stock_threshold': 5,
            'track_inventory': True,
            'requires_shipping': True,
            'sku': f"TEST{timezone.now().strftime('%Y%m%d%H%M%S')}",
            'weight': Decimal('1.00'),
            'manufacturing_cost': Decimal('5.00'),
            'packaging_cost': Decimal('1.00'),
            'shipping_to_warehouse_cost': Decimal('0.50'),
        }
        
        # Add product type specific defaults
        if product_type == ProductType.DIGITAL:
            defaults.update({
                'download_limit': 5,
                'access_duration': timedelta(days=30),
                'file_size': 1024 * 1024,  # 1MB
                'file_type': 'pdf',
                'requires_shipping': False,
            })
        elif product_type == ProductType.SERVICE:
            defaults.update({
                'service_type': 'CONSULTATION',
                'duration': timedelta(hours=1),
                'location_required': False,
                'provider_notes': 'Test service notes',
            })
            if 'location' not in kwargs:
                defaults['location'] = location_factory()
        
        # Update with any provided kwargs, allowing overrides of defaults
        defaults.update(kwargs)
        
        # Create the product instance without saving
        product = Product.objects.create(**{k: v for k, v in defaults.items()
                           if not k.startswith('_')})
        
        return product
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


