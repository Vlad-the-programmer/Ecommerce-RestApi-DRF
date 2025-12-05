from decimal import Decimal

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, F, Case, When, Value, DecimalField, Count, Avg, DurationField
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

from common.permissions import IsAdminOrOwner
from .models import Invoice
from .serializers import (
    InvoiceCreateSerializer,
    InvoiceUpdateSerializer,
    InvoiceListSerializer,
    InvoiceDetailSerializer
)
from .enums import InvoiceStatus
from common.utlis import send_email_confirmation


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows invoices to be viewed or edited.
    """
    queryset = Invoice.objects.all()
    serializer_class = InvoiceListSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwner]
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = {
        'status': ['exact', 'in'],
        'issue_date': ['date', 'date__gt', 'date__lt', 'date__gte', 'date__lte'],
        'due_date': ['date', 'date__gt', 'date__lt', 'date__gte', 'date__lte'],
        'total_amount': ['exact', 'gt', 'lt', 'gte', 'lte'],
        'is_paid': ['exact'],
        'is_overdue': ['exact'],
    }
    ordering_fields = ['issue_date', 'due_date', 'total_amount', 'date_created']
    search_fields = ['invoice_number', 'user__email', 'user__first_name', 'user__last_name', 'notes']

    def get_serializer_class(self):
        if self.action == 'create':
            return InvoiceCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return InvoiceUpdateSerializer
        elif self.action == 'retrieve':
            return InvoiceDetailSerializer
        return self.serializer_class

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        Regular users can only see their own invoices.
        Staff users can see all invoices.
        """
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)

        queryset = queryset.annotate(
            amount_due=Case(
                When(
                    status__in=[InvoiceStatus.PAID, InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED],
                    then=Value(0)
                ),
                default=F('total_amount') - F('amount_paid'),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )

        return queryset.select_related('user', 'order').prefetch_related('items')

    def perform_create(self, serializer):
        """Set the user to the current user when creating an invoice."""
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_as_paid(self, request, pk=None):
        """Mark an invoice as paid."""
        invoice = self.get_object()

        if invoice.status == InvoiceStatus.PAID:
            return Response(
                {'detail': _('Invoice is already marked as paid.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        invoice.mark_paid()

        return Response({'status': 'Invoice marked as paid'})

    @action(detail=True, methods=['post'])
    def send_invoice(self, request, pk=None):
        """Send invoice to the customer."""
        invoice = self.get_object()

        if invoice.status == InvoiceStatus.DRAFT:
            invoice.status = InvoiceStatus.ISSUED
            invoice.sent_at = timezone.now()
            invoice.save()

            # TODO: Send email to customer
            # send_invoice_email.delay(invoice.id)

            return Response({'status': 'Invoice sent successfully'})

        return Response(
            {'detail': _('Only draft invoices can be sent.')},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get invoice statistics."""
        queryset = self.filter_queryset(self.get_queryset())

        stats = {
            'total_invoices': queryset.count(),
            'total_amount': float(queryset.aggregate(total=Sum('total_amount'))['total'] or 0),
            'total_paid': float(
                queryset.filter(status=InvoiceStatus.PAID).aggregate(total=Sum('total_amount'))['total'] or 0),
            'total_due': float(
                queryset.exclude(status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.OVERDUE])
                .annotate(amount_due=F('total_amount') - F('amount_paid'))
                .aggregate(total=Sum('amount_due'))['total'] or 0),
        }

        status_stats = queryset.values('status').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        ).order_by('-count')

        stats['by_status'] = {
            item['status']: {
                'count': item['count'],
                'total': float(item['total'] or 0)
            }
            for item in status_stats
        }

        # Monthly trends
        monthly_stats = queryset.filter(
            issue_date__isnull=False
        ).annotate(
            month=TruncMonth('issue_date')
        ).values('month').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        ).order_by('month')

        stats['monthly_trends'] = [
            {
                'month': item['month'].strftime('%Y-%m'),
                'count': item['count'],
                'total': float(item['total'] or 0)
            }
            for item in monthly_stats
        ]

        overdue = queryset.filter(
            status__in=[InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE],
            due_date__lt=timezone.now().date()
        ).aggregate(
            count=Count('id'),
            total=Sum('total_amount') - Sum('amount_paid')
        )

        stats['overdue'] = {
            'count': overdue['count'] or 0,
            'amount': float(overdue['total'] or 0)
        }

        payment_timing = queryset.exclude(paid_at__isnull=True).aggregate(
            avg_days_to_pay=Avg(
                F('paid_at') - F('issue_date'),
                output_field=DurationField()
            )
        )

        stats['payment_timing'] = {
            'avg_days_to_pay': payment_timing['avg_days_to_pay'].days if payment_timing['avg_days_to_pay'] else None
        }

        return Response(stats)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get a summary of invoices for the current user."""
        from django.db.models.functions import TruncMonth

        queryset = self.filter_queryset(self.get_queryset())

        # Get current date and calculate dates for filtering
        today = timezone.now().date()
        start_of_month = today.replace(day=1)
        start_of_year = today.replace(month=1, day=1)

        monthly_summary = queryset.filter(
            issue_date__year=today.year
        ).annotate(
            month=TruncMonth('issue_date')
        ).values('month').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        ).order_by('month')

        status_summary = queryset.values('status').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        )

        overdue_summary = queryset.filter(
            due_date__lt=today,
            status__in=[InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE, InvoiceStatus.PAID]
        ).aggregate(
            count=Count('id'),
            total=Sum('total_amount') - Sum('amount_paid')
        )

        ytd_summary = queryset.filter(
            issue_date__year=today.year
        ).aggregate(
            count=Count('id'),
            total=Sum('total_amount')
        )

        mtd_summary = queryset.filter(
            issue_date__year=today.year,
            issue_date__month=today.month
        ).aggregate(
            count=Count('id'),
            total=Sum('total_amount')
        )

        return Response({
            'monthly_summary': [
                {
                    'month': item['month'].strftime('%Y-%m'),
                    'count': item['count'],
                    'total': float(item['total'] or 0)
                }
                for item in monthly_summary
            ],
            'status_summary': {
                item['status']: {
                    'count': item['count'],
                    'total': float(item['total'] or 0)
                }
                for item in status_summary
            },
            'overdue': {
                'count': overdue_summary['count'] or 0,
                'amount': float(overdue_summary['total'] or 0) if overdue_summary['total'] is not None else 0
            },
            'year_to_date': {
                'count': ytd_summary['count'] or 0,
                'total': float(ytd_summary['total'] or 0)
            },
            'month_to_date': {
                'count': mtd_summary['count'] or 0,
                'total': float(mtd_summary['total'] or 0)
            }
        })

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """Add a payment to an invoice."""

        invoice = self.get_object()
        amount = Decimal(request.data.get('amount', 0))

        if amount <= 0:
            return Response(
                {'amount': ['Payment amount must be greater than zero.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        if invoice.status in [InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.DRAFT]:
            return Response(
                {'detail': _('Cannot add payment to a %(status)s invoice.')
                           % {'status': invoice.get_status_display()}},
                status=status.HTTP_400_BAD_REQUEST
            )

        invoice.amount_paid = (invoice.amount_paid or 0) + amount
        if invoice.amount_paid >= invoice.total_amount:
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = timezone.now()
        else:
            return Response(
                {'amount': ['Payment amount must be greater than invoice amount.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment = invoice.add_payment(amount,
                            request.data.get('payment_method', 'bank_transfer'),
                            request.data.get('notes')
        )

        # TODO: Send payment confirmation email
        # send_payment_confirmation.delay(payment.id)

        send_email_confirmation(
            subject='Payment Confirmation',
            template_name='invoices/email/payment_confirm',
            context={
                'recipient_name': f"{invoice.user.first_name} {invoice.user.last_name}",
                'payment_description': f"Payment for Invoice #{invoice.invoice_number}",
                'amount': amount,
                'currency': invoice.currency,
                'payment_method': payment.payment_method,
                'transaction_id': payment.payment_reference,
                'date': timezone.now(),
                'site_name': getattr(settings, 'SITE_NAME', 'Your E-commerce Site'),
                'site_url': getattr(settings, 'SITE_URL', 'https://your-ecommerce-site.com'),
                },
            to_emails=[invoice.customer.email]
        )

        return Response({
            'status': 'Payment added successfully',
            'invoice_id': invoice.id,
            'payment_id': payment.uuid,
            'amount_paid': str(amount),
            'new_status': invoice.status
        }, status=status.HTTP_201_CREATED)