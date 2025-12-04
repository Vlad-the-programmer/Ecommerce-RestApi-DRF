import pytest
from decimal import Decimal
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from payments.enums import PaymentStatus, PaymentMethod
from payments.models import Payment
from tests.unit.payments.conftest import payment_factory

pytestmark = pytest.mark.django_db


class TestPaymentViewSet:
    """Test PaymentViewSet."""
    def test_list_payments(self, authenticated_client, payment_list_url, payment_factory):
        """Test retrieving a list of payments."""
        payment_factory.create_batch(2, user=self.user)
        
        response = authenticated_client.get(payment_list_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3  # 1 from setUp + 2 created here

    def test_retrieve_payment(self, authenticated_client, payment_detail_url, payment_factory):
        """Test retrieving a single payment."""
        payment = payment_factory(conirmed_at=timezone.now())
        url = payment_detail_url(payment.id)
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == str(payment.id)
        assert response.data['amount'] == str(payment.amount)

    def test_create_payment(self, authenticated_client, payment_list_url, order_factory, verified_user):
        """Test creating a new payment."""
        user, _, _, _ = verified_user
        order = order_factory(user=user)
        data = {
            'order': order.id,
            'amount': '199.99',
            'currency': 'EUR',
            'method': PaymentMethod.PAYPAL,
            'notes': 'Test payment creation'
        }
        
        response = authenticated_client.post(payment_list_url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['amount'] == '199.99'
        assert response.data['status'] == PaymentStatus.PENDING
        assert response.data['user'] == user.id

    def test_update_payment(self, authenticated_client, payment_detail_url, payment_factory):
        """Test updating a payment status."""
        payment = payment_factory(conirmed_at=timezone.now())
        url = payment_detail_url(payment.id)
        data = {
            'status': PaymentStatus.COMPLETED,
            'notes': 'Payment completed'
        }
        
        response = authenticated_client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == PaymentStatus.COMPLETED
        assert response.data['notes'] == 'Payment completed'

    def test_delete_payment(self, authenticated_client, payment_detail_url, payment_factory):
        """Test deleting a payment."""
        payment = payment_factory(conirmed_at=timezone.now())
        url = payment_detail_url(payment.id)
        response = authenticated_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Payment.objects.filter(id=payment.id).exists()

    def test_mark_as_completed(self, authenticated_client, payment_factory):
        """Test marking a payment as completed."""
        payment = payment_factory(status=PaymentStatus.PENDING)
        url = reverse('v1:payment-mark-as-completed', kwargs={'pk': payment.id})
        
        response = authenticated_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.COMPLETED
        assert payment.confirmed_at is not None

    def test_payment_summary(self, client, payment_factory, payment_list_url):
        """Test getting payment summary statistics."""
        payment_factory(
            status=PaymentStatus.COMPLETED,
            amount=Decimal('100.00')
        )
        payment_factory(
            status=PaymentStatus.COMPLETED,
            amount=Decimal('200.00'),
            method=PaymentMethod.BANK_TRANSFER
        )
        payment_factory(
            status=PaymentStatus.FAILED,
            amount=Decimal('50.00')
        )
        
        url = f"{payment_list_url}summary/"
        response = client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        assert data['total_payments'] == 3
        assert data['total_amount'] == '350.00'
        
        status_summary = {item['status']: item for item in data['by_status']}
        assert status_summary[PaymentStatus.COMPLETED]['count'] == 2
        assert status_summary[PaymentStatus.COMPLETED]['amount'] == '300.00'
        assert status_summary[PaymentStatus.FAILED]['count'] == 1
        assert status_summary[PaymentStatus.FAILED]['amount'] == '50.00'
        
        method_summary = {item['method']: item for item in data['by_method']}
        assert method_summary[PaymentMethod.CREDIT_CARD]['count'] == 2
        assert method_summary[PaymentMethod.BANK_TRANSFER]['count'] == 1
