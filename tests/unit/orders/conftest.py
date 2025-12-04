import pytest
from decimal import Decimal
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, OrderItem, OrderTax, OrderStatusHistory
from orders.enums import OrderStatuses
from tests.unit.cart.conftest import cart_item_factory, cart_factory
from tests.unit.products.conftest import product_factory


@pytest.fixture
def order_list_url():
    """URL for order list endpoint."""
    return reverse('v1:order-list')


@pytest.fixture
def order_detail_url():
    """URL factory for order detail endpoint."""
    def _order_detail_url(order_id):
        return reverse('v1:order-detail', kwargs={'pk': order_id})
    return _order_detail_url


@pytest.fixture
def order_item_list_url():
    """URL for order item list endpoint."""
    return reverse('v1:orderitem-list')


@pytest.fixture
def order_item_detail_url():
    """URL factory for order item detail endpoint."""
    def _order_item_detail_url(item_id):
        return reverse('v1:orderitem-detail', kwargs={'pk': item_id})
    return _order_item_detail_url


@pytest.fixture
def order_status_history_list_url():
    """URL for order status history list endpoint."""
    return reverse('v1:orderstatushistory-list')


@pytest.fixture
def order_status_history_detail_url():
    """URL factory for order status history detail endpoint."""
    def _order_status_history_detail_url(history_id):
        return reverse('v1:orderstatushistory-detail', kwargs={'pk': history_id})
    return _order_status_history_detail_url


@pytest.fixture
def order_tax_list_url():
    """URL for order tax list endpoint."""
    return reverse('v1:ordertax-list')


@pytest.fixture
def order_tax_detail_url():
    """URL factory for order tax detail endpoint."""
    def _order_tax_detail_url(tax_id):
        return reverse('v1:ordertax-detail', kwargs={'pk': tax_id})
    return _order_tax_detail_url


@pytest.fixture
def order_factory(db, verified_user, cart_factory, product_factory, cart_item_factory):
    """Create an order factory fixture."""
    def _create_order(**kwargs):
        # Create a cart with items if not provided
        if 'cart' not in kwargs:
            cart = cart_factory(user=kwargs.get('user', verified_user))
            product = product_factory(price=Decimal('100.00'))
            cart_item_factory(cart=cart, product=product, quantity=2)
            kwargs['cart'] = cart
        
        defaults = {
            'user': verified_user,
            'status': OrderStatuses.PENDING,
            'total_amount': Decimal('200.00'),
        }
        defaults.update(kwargs)
        
        order = Order.objects.create(**defaults)
        return order
    return _create_order


@pytest.fixture
def order_item_factory(db, order_factory, product_factory):
    """Create an order item factory fixture."""
    def _create_order_item(**kwargs):
        if 'order' not in kwargs:
            order = order_factory()
            kwargs['order'] = order
        
        if 'product' not in kwargs:
            kwargs['product'] = product_factory(price=Decimal('50.00'))
        
        defaults = {
            'quantity': 2,
            'total_price': Decimal('100.00'),
        }
        defaults.update(kwargs)
        
        return OrderItem.objects.create(**defaults)
    return _create_order_item


@pytest.fixture
def order_tax_factory(db, order_factory):
    """Create an order tax factory fixture."""
    def _create_order_tax(**kwargs):
        if 'order' not in kwargs:
            order = order_factory()
            kwargs['order'] = order
        
        defaults = {
            'name': 'VAT',
            'rate': Decimal('0.23'),  # 23%
            'amount': Decimal('100.00'),
            'tax_value': Decimal('23.00'),
            'amount_with_taxes': Decimal('123.00'),
        }
        defaults.update(kwargs)
        
        return OrderTax.objects.create(**defaults)
    return _create_order_tax


@pytest.fixture
def order_status_history_factory(db, order_factory, admin_user):
    """Create an order status history factory fixture."""
    def _create_order_status_history(**kwargs):
        if 'order' not in kwargs:
            order = order_factory()
            kwargs['order'] = order
        
        if 'status' not in kwargs:
            kwargs['status'] = OrderStatuses.PENDING
        
        if 'changed_by' not in kwargs:
            kwargs['changed_by'] = admin_user
        
        defaults = {
            'notes': 'Status changed',
        }
        defaults.update(kwargs)
        
        return OrderStatusHistory.objects.create(**defaults)
    return _create_order_status_history
