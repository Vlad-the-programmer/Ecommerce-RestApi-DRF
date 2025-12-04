import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from django.urls import reverse
from django.utils import timezone

from payments.models import Payment
from payments.enums import PaymentStatus, PaymentMethod
from tests.unit.orders.conftest import order_factory
from tests.unit.orders.conftest import order_factory


@pytest.fixture
def payment_list_url():
    """URL for payment list endpoint."""
    return reverse('v1:payment-list')


@pytest.fixture
def payment_detail_url():
    """URL factory for payment detail endpoint."""
    def _payment_detail_url(payment_id):
        return reverse('v1:payment-detail', kwargs={'pk': payment_id})
    return _payment_detail_url


@pytest.fixture
def payment_factory(db, order_factory, verified_user):
    """Create a payment factory fixture."""
    def _payment_factory(
        order=None,
        customer=None,
        payment_reference=None,
        amount=Decimal('100.00'),
        currency='USD',
        method=PaymentMethod.CREDIT_CARD,
        status=PaymentStatus.PENDING,
        transaction_date=None,
        confirmed_at=None,
        notes=None,
        **kwargs
    ):
        user, _, _, _ = verified_user if isinstance(verified_user, tuple) else (verified_user, None, None, None)
        
        user = customer or user
        
        if order is None:
            order = order_factory(user=user)
        
        if transaction_date is None:
            transaction_date = timezone.now()
            
        payment = Payment.objects.create(
            order=order,
            user=user,
            payment_reference=payment_reference or f"PAY-{datetime.now().timestamp()}",
            amount=amount,
            currency=currency,
            method=method,
            status=status,
            transaction_date=transaction_date,
            confirmed_at=confirmed_at,
            notes=notes or "",
            **kwargs
        )
        return payment
    return _payment_factory
