import pytest
from decimal import Decimal
from datetime import datetime, timezone

from payments.serializers import (
    PaymentSerializer,
    PaymentCreateSerializer,
    PaymentUpdateSerializer
)
from payments.enums import PaymentStatus, PaymentMethod
from tests.unit.orders.conftest import order_factory

pytestmark = pytest.mark.django_db

class TestPaymentSerializer:
    def test_serialize_payment(self, payment_factory):
        """Test serialization of a payment."""
        payment = payment_factory(
            amount=Decimal('99.99'),
            currency='EUR',
            method=PaymentMethod.PAYPAL,
            status=PaymentStatus.COMPLETED,
            notes='Test payment'
        )
        
        serializer = PaymentSerializer(payment)
        data = serializer.data
        
        assert data['id'] == str(payment.id)
        assert data['amount'] == '99.99'
        assert data['currency'] == 'EUR'
        assert data['method'] == PaymentMethod.PAYPAL
        assert data['status'] == PaymentStatus.COMPLETED
        assert data['notes'] == 'Test payment'
        assert 'method_display' in data
        assert 'status_display' in data
        assert 'transaction_date' in data
        assert 'date_created' in data
        assert 'date_updated' in data


class TestPaymentCreateSerializer:
    def test_create_payment(self, order_factory, verified_user):
        """Test creating a new payment."""
        order = order_factory()
        data = {
            'order': order.id,
            'amount': '150.50',
            'currency': 'USD',
            'method': PaymentMethod.CREDIT_CARD,
            'notes': 'Test creation'
        }
        
        serializer = PaymentCreateSerializer(
            data=data,
            context={'request': type('Request', (), {'user': verified_user})}
        )
        assert serializer.is_valid(), serializer.errors
        
        payment = serializer.save()
        assert payment.amount == Decimal('150.50')
        assert payment.currency == 'USD'
        assert payment.method == PaymentMethod.CREDIT_CARD
        assert payment.status == PaymentStatus.PENDING
        assert payment.user == verified_user
        assert payment.order == order


class TestPaymentUpdateSerializer:
    def test_update_payment(self, payment_factory):
        """Test updating a payment."""
        payment = payment_factory(
            status=PaymentStatus.PENDING,
            notes='Old note'
        )
        
        data = {
            'status': PaymentStatus.COMPLETED,
            'notes': 'Updated note'
        }
        
        serializer = PaymentUpdateSerializer(
            instance=payment,
            data=data,
            partial=True
        )
        assert serializer.is_valid(), serializer.errors
        
        updated_payment = serializer.save()
        assert updated_payment.status == PaymentStatus.COMPLETED
        assert updated_payment.notes == 'Updated note'
    
    def test_cannot_update_immutable_fields(self, payment_factory):
        """Test that immutable fields cannot be updated."""
        payment = payment_factory(amount=Decimal('100.00'))
        
        data = {
            'amount': '200.00',  # Should not be updatable
            'currency': 'EUR',   # Should not be updatable
            'method': PaymentMethod.BANK_TRANSFER  # Should not be updatable
        }
        
        serializer = PaymentUpdateSerializer(
            instance=payment,
            data=data,
            partial=True
        )
        assert serializer.is_valid()
        
        updated_payment = serializer.save()
        assert updated_payment.amount == Decimal('100.00')
        assert updated_payment.currency == 'USD'  # Default from factory
        assert updated_payment.method == PaymentMethod.CREDIT_CARD  # Default from factory
