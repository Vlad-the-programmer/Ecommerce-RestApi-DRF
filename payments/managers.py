from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from common.managers import SoftDeleteManager
from payments.enums import PaymentStatus


class PaymentManager(SoftDeleteManager):
    """
    Custom manager for Payment model with payment-specific methods.
    Inherits from your base SoftDeleteManager.
    """

    def successful(self):
        """Get all successful payments"""
        from .enums import PaymentStatus
        return self.get_queryset().filter(status=PaymentStatus.COMPLETED)

    def pending(self):
        """Get all pending payments"""
        from .enums import PaymentStatus
        return self.get_queryset().filter(status=PaymentStatus.PENDING)

    def failed(self):
        """Get all failed payments"""
        from .enums import PaymentStatus
        return self.with_deleted().filter(status=PaymentStatus.FAILED)

    def refunded(self):
        """Get all refunded payments"""
        from .enums import PaymentStatus
        return self.with_deleted().filter(status=PaymentStatus.REFUNDED)

    def cancelled(self):
        """Get all cancelled payments"""
        from .enums import PaymentStatus
        return self.with_deleted().filter(status=PaymentStatus.CANCELLED)

    # Payment Method Filters
    def by_method(self, method):
        """Get payments by specific method"""
        return self.get_queryset().filter(method=method)

    def credit_card_payments(self):
        """Get all credit card payments"""
        from .enums import PaymentMethod
        return self.by_method(PaymentMethod.CREDIT_CARD)

    def paypal_payments(self):
        """Get all PayPal payments"""
        from .enums import PaymentMethod
        return self.by_method(PaymentMethod.PAYPAL)

    def bank_transfer_payments(self):
        """Get all bank transfer payments"""
        from .enums import PaymentMethod
        return self.by_method(PaymentMethod.BANK_TRANSFER)

    def for_user(self, user):
        """Get all payments for a specific user"""
        return self.get_queryset().filter(user=user)

    def for_invoice(self, invoice):
        """Get all payments for a specific invoice"""
        return self.get_queryset().filter(invoice=invoice)

    def for_invoice_number(self, invoice_number):
        """Get payments by invoice number"""
        return self.get_queryset().filter(invoice__invoice_number=invoice_number)

    def today(self):
        """Get payments from today"""
        today = timezone.now().date()
        return self.get_queryset().filter(
            transaction_date__date=today
        )

    def this_week(self):
        """Get payments from this week"""
        week_ago = timezone.now() - timedelta(days=7)
        return self.get_queryset().filter(
            transaction_date__gte=week_ago
        )

    def this_month(self):
        """Get payments from this month"""
        month_ago = timezone.now() - timedelta(days=30)
        return self.get_queryset().filter(
            transaction_date__gte=month_ago
        )

    def between_dates(self, start_date, end_date):
        """Get payments between specific dates"""
        return self.get_queryset().filter(
            transaction_date__range=[start_date, end_date]
        )

    def recent(self, days=30):
        """Get recent payments within specified days"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.get_queryset().filter(
            transaction_date__gte=cutoff_date
        )

    def above_amount(self, amount):
        """Get payments above specified amount"""
        return self.get_queryset().filter(amount__gte=amount)

    def below_amount(self, amount):
        """Get payments below specified amount"""
        return self.get_queryset().filter(amount__lte=amount)

    def in_amount_range(self, min_amount, max_amount):
        """Get payments within amount range"""
        return self.get_queryset().filter(
            amount__gte=min_amount,
            amount__lte=max_amount
        )

    def in_currency(self, currency):
        """Get payments in specific currency"""
        return self.get_queryset().filter(currency=currency)

    def usd_payments(self):
        """Get all USD payments"""
        return self.in_currency('USD')

    def eur_payments(self):
        """Get all EUR payments"""
        return self.in_currency('EUR')

    def total_amount(self, **filters):
        """Calculate total amount of payments with optional filters"""
        queryset = self.get_queryset().filter(**filters)
        return queryset.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    def average_amount(self, **filters):
        """Calculate average payment amount"""
        queryset = self.get_queryset().filter(**filters)
        return queryset.aggregate(avg=Avg('amount'))['avg'] or Decimal('0.00')

    def payment_count(self, **filters):
        """Count payments with optional filters"""
        return self.get_queryset().filter(**filters).count()

    def success_rate(self):
        """Calculate payment success rate"""
        total = self.get_queryset().count()
        if total == 0:
            return 0
        successful = self.successful().count()
        return (successful / total) * 100

    def revenue_by_currency(self):
        """Get total revenue grouped by currency"""
        return self.get_queryset().values('currency').annotate(
            total_revenue=Sum('amount'),
            payment_count=Count('id')
        ).order_by('-total_revenue')

    def revenue_by_method(self):
        """Get total revenue grouped by payment method"""
        return self.get_queryset().values('method').annotate(
            total_revenue=Sum('amount'),
            payment_count=Count('id'),
            success_rate=(
                    Count('id', filter=Q(status='COMPLETED')) * 100.0 /
                    Count('id')
            )
        ).order_by('-total_revenue')

    def monthly_revenue(self, months=12):
        """Get monthly revenue for specified number of months"""
        from django.db.models.functions import TruncMonth
        cutoff_date = timezone.now() - timedelta(days=30 * months)

        return self.get_queryset().filter(
            transaction_date__gte=cutoff_date,
            status=PaymentStatus.COMPLETED
        ).annotate(
            month=TruncMonth('transaction_date')
        ).values('month').annotate(
            total_revenue=Sum('amount'),
            payment_count=Count('id')
        ).order_by('month')

    def get_by_reference(self, reference):
        """Get payment by reference number"""
        return self.get_queryset().filter(payment_reference=reference).first()

    def get_user_total_paid(self, user):
        """Get total amount paid by a user"""
        return self.for_user(user).filter(status=PaymentStatus.COMPLETED).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

    def get_invoice_total_paid(self, invoice):
        """Get total amount paid for an invoice"""
        return self.for_invoice(invoice).filter(status=PaymentStatus.COMPLETED).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

    def find_duplicate_payments(self, invoice, amount, within_minutes=5):
        """Find potential duplicate payments for same invoice and amount"""
        time_threshold = timezone.now() - timedelta(minutes=within_minutes)
        return self.get_queryset().filter(
            invoice=invoice,
            amount=amount,
            transaction_date__gte=time_threshold
        ).exclude(status__in=[PaymentStatus.FAILED, PaymentStatus.CANCELLED])

    def get_pending_payments_older_than(self, hours=24):
        """Get pending payments older than specified hours for cleanup"""
        cutoff_time = timezone.now() - timedelta(hours=hours)
        return self.pending().filter(
            transaction_date__lt=cutoff_time
        )

    def mark_old_pendings_as_failed(self, hours=24):
        """Mark old pending payments as failed"""
        old_pendings = self.get_pending_payments_older_than(hours)
        for payment in old_pendings:
            payment.status = PaymentStatus.FAILED

        self.bulk_update(old_pendings, fields=["status"])
        return old_pendings.count()

    # Performance Optimized Queries
    def with_invoice_details(self):
        """Prefetch related invoice details"""
        return self.get_queryset().select_related('invoice', 'user')

    def with_user_details(self):
        """Prefetch related user details"""
        return self.get_queryset().select_related('user')

    def for_dashboard(self):
        """Optimized query for dashboard display"""
        return self.with_invoice_details().select_related('user').only(
            'payment_reference',
            'amount',
            'currency',
            'method',
            'status',
            'transaction_date',
            'invoice__invoice_number',
            'user__email'
        )