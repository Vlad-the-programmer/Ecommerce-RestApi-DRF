"""Tests for orders app views."""
import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from unittest.mock import patch

from orders.enums import OrderStatuses
from orders.models import Order, OrderStatusHistory, OrderItem


class TestOrderViewSet:
    """Test cases for OrderViewSet."""
    
    def test_list_orders_authenticated(self, authenticated_client, order_factory):
        """Test that authenticated users can list their own orders."""
        # Create 3 orders for the authenticated user
        order_factory.create_batch(3, user=authenticated_client.user)
        
        # Create some orders for another user (shouldn't be visible)
        order_factory.create_batch(2)
        
        url = reverse('v1:order-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3
    
    def test_list_orders_unauthenticated(self, client):
        """Test that unauthenticated users cannot list orders."""
        url = reverse('v1:order-list')
        response = client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_retrieve_order_owner(self, authenticated_client, order_factory):
        """Test that order owners can retrieve their own order."""
        order = order_factory(user=authenticated_client.user)
        url = reverse('v1:order-detail', kwargs={'pk': order.id})
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == order.id
    
    def test_retrieve_order_not_owner(self, authenticated_client, order_factory):
        """Test that users cannot retrieve orders they don't own."""
        order = order_factory()  # Different user
        url = reverse('v1:order-detail', kwargs={'pk': order.id})
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_create_order(self, authenticated_client, cart_factory, cart_item_factory, product_factory):
        """Test creating a new order from cart."""
        # Create a cart with items for the authenticated user
        cart = cart_factory(user=authenticated_client)
        product = product_factory(price=Decimal('50.00'))
        cart_item = cart_item_factory(cart=cart, product=product, quantity=2)
        
        data = {
            'shipping_class': 'standard',
            'shipping_address': '123 Test St, Test City',
        }
        
        url = reverse('v1:order-list')
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert Order.objects.count() == 1
        assert OrderItem.objects.count() == 1
        assert response.data['status'] == OrderStatuses.PENDING
        assert Decimal(response.data['total_amount']) == Decimal('100.00')
    
    def test_cancel_order(self, authenticated_client, order_factory):
        """Test canceling an order."""
        order = order_factory(user=authenticated_client.user, status=OrderStatuses.PENDING)
        url = reverse('v1:order-cancel', kwargs={'pk': order.id})
        
        response = authenticated_client.post(url)
        
        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == OrderStatuses.CANCELLED
        assert OrderStatusHistory.objects.filter(order=order, status=OrderStatuses.CANCELLED).exists()
    
    def test_cancel_order_invalid_status(self, authenticated_client, order_factory):
        """Test canceling an order that cannot be canceled."""
        order = order_factory(user=authenticated_client.user, status=OrderStatuses.COMPLETED)
        url = reverse('v1:order-cancel', kwargs={'pk': order.id})
        
        response = authenticated_client.post(url)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'cannot be cancelled' in str(response.data['detail'])


class TestOrderItemViewSet:
    """Test cases for OrderItemViewSet."""
    
    def test_list_order_items_owner(self, authenticated_client, order_item_factory):
        """Test that order owners can list their order items."""
        # Create order items for the authenticated user
        order_item1 = order_item_factory(order__user=authenticated_client.user)
        order_item2 = order_item_factory(order__user=authenticated_client.user)
        
        # Create some order items for another user (shouldn't be visible)
        order_item_factory()
        
        url = reverse('v1:orderitem-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
        order_item_ids = {item['id'] for item in response.data['results']}
        assert order_item1.id in order_item_ids
        assert order_item2.id in order_item_ids
    
    def test_retrieve_order_item_owner(self, authenticated_client, order_item_factory):
        """Test that order owners can retrieve their order items."""
        order_item = order_item_factory(order__user=authenticated_client.user)
        url = reverse('v1:orderitem-detail', kwargs={'pk': order_item.id})
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == order_item.id
    
    def test_retrieve_order_item_not_owner(self, authenticated_client, order_item_factory):
        """Test that users cannot retrieve order items they don't own."""
        order_item = order_item_factory()  # Different user
        url = reverse('v1:orderitem-detail', kwargs={'pk': order_item.id})
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestOrderStatusHistoryViewSet:
    """Test cases for OrderStatusHistoryViewSet."""
    
    def test_list_status_history_owner(self, authenticated_client, order_status_history_factory):
        """Test that order owners can list their order status history."""
        # Create status history for the authenticated user's order
        history1 = order_status_history_factory(order__user=authenticated_client.user)
        history2 = order_status_history_factory(order=history1.order)  # Same order
        
        # Create status history for another user's order (shouldn't be visible)
        order_status_history_factory()
        
        url = reverse('v1:orderstatushistory-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
        history_ids = {item['id'] for item in response.data['results']}
        assert history1.id in history_ids
        assert history2.id in history_ids
    
    def test_retrieve_status_history_owner(self, authenticated_client, order_status_history_factory):
        """Test that order owners can retrieve their order status history."""
        history = order_status_history_factory(order__user=authenticated_client.user)
        url = reverse('v1:orderstatushistory-detail', kwargs={'pk': history.id})
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == history.id


class TestAdminOrderViewSet:
    """Test cases for AdminOrderViewSet."""
    
    def test_list_orders_admin(self, admin_client, order_factory):
        """Test that admin can list all orders."""
        # Create orders for different users
        order_factory.create_batch(3)
        
        url = reverse('v1:admin-order-list')
        response = admin_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3
    
    def test_update_status_admin(self, admin_client, order_factory):
        """Test that admin can update order status."""
        order = order_factory(status=OrderStatuses.PENDING)
        url = reverse('v1:admin-order-update-status', kwargs={'pk': order.id})
        
        data = {
            'status': OrderStatuses.PROCESSING,
            'notes': 'Order is being processed'
        }
        
        response = admin_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == OrderStatuses.PROCESSING
        assert OrderStatusHistory.objects.filter(
            order=order, 
            status=OrderStatuses.PROCESSING,
            notes='Order is being processed'
        ).exists()
    
    def test_update_status_invalid(self, admin_client, order_factory):
        """Test updating order status with invalid status."""
        order = order_factory()
        url = reverse('v1:admin-order-update-status', kwargs={'pk': order.id})
        
        data = {
            'status': 'INVALID_STATUS',
            'notes': 'Invalid status test'
        }
        
        response = admin_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Invalid status' in str(response.data['status'])


class TestOrderTaxViewSet:
    """Test cases for OrderTaxViewSet."""
    
    def test_list_order_taxes_owner(self, authenticated_client, order_tax_factory):
        """Test that order owners can list their order taxes."""
        # Create taxes for the authenticated user's order
        tax1 = order_tax_factory(order__user=authenticated_client.user)
        tax2 = order_tax_factory(order=tax1.order)  # Same order
        
        # Create taxes for another user's order (shouldn't be visible)
        order_tax_factory()
        
        url = reverse('v1:ordertax-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
        tax_ids = {item['id'] for item in response.data['results']}
        assert tax1.id in tax_ids
        assert tax2.id in tax_ids
    
    def test_retrieve_order_tax_owner(self, authenticated_client, order_tax_factory):
        """Test that order owners can retrieve their order taxes."""
        tax = order_tax_factory(order__user=authenticated_client.user)
        url = reverse('v1:ordertax-detail', kwargs={'pk': tax.id})
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == tax.id
        assert response.data['name'] == 'VAT'
        assert response.data['rate'] == '0.23'
