from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import Invoice
from .enums import InvoiceStatus


class InvoiceItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    description = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)


class InvoiceCreateSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, required=True)
    status = serializers.ChoiceField(
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        required=False
    )

    class Meta:
        model = Invoice
        fields = [
            'user', 'order', 'invoice_number', 'status', 'issue_date', 'due_date',
            'currency', 'subtotal', 'tax_amount', 'discount_amount', 'total_amount',
            'notes', 'terms', 'items'
        ]
        read_only_fields = ['subtotal', 'tax_amount', 'total_amount']
        extra_kwargs = {
            'invoice_number': {'required': False},
            'currency': {'default': 'USD'},
            'issue_date': {'required': False},
            'due_date': {'required': False}
        }

    def validate(self, data):
        if 'due_date' in data and 'issue_date' in data:
            if data['due_date'] < data['issue_date']:
                raise serializers.ValidationError({
                    'due_date': _("Due date cannot be before issue date.")
                })
        return data

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        invoice = Invoice.objects.create(**validated_data)

        subtotal = 0
        tax_total = 0

        for item_data in items_data:
            amount = item_data['quantity'] * item_data['unit_price']
            tax_amount = amount * (item_data['tax_rate'] / 100)

            subtotal += amount
            tax_total += tax_amount

            invoice.items.create(
                description=item_data['description'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                amount=amount,
                tax_rate=item_data['tax_rate'],
                tax_amount=tax_amount,
                total_amount=amount + tax_amount
            )

        invoice.subtotal = subtotal
        invoice.tax_amount = tax_total
        invoice.total_amount = subtotal + tax_total - (invoice.discount_amount or 0)
        invoice.save()

        return invoice


class InvoiceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            'status', 'due_date', 'notes', 'terms', 'payment_terms',
            'discount_amount', 'is_paid'
        ]
        read_only_fields = ['user', 'order', 'invoice_number', 'issue_date', 'subtotal', 'tax_amount', 'total_amount']

    def validate_status(self, value):
        instance = self.instance
        if instance and instance.status == InvoiceStatus.PAID and value != InvoiceStatus.PAID:
            raise serializers.ValidationError(
                _("Cannot change status from paid to another status.")
            )
        return value


class InvoiceListSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)
    amount_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'user', 'status', 'status_display',
            'issue_date', 'due_date', 'total_amount', 'amount_paid',
            'amount_due', 'days_overdue', 'is_paid', 'is_overdue'
        ]
        read_only_fields = fields


class InvoiceDetailSerializer(InvoiceListSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    order = serializers.HyperlinkedRelatedField(
        view_name='v1:order-detail',
        lookup_field='pk',
        read_only=True
    )
    payment_url = serializers.SerializerMethodField()

    class Meta(InvoiceListSerializer.Meta):
        fields = InvoiceListSerializer.Meta.fields + [
            'order', 'currency', 'subtotal', 'tax_amount', 'discount_amount',
            'notes', 'terms', 'payment_terms', 'payment_url', 'items'
        ]

    def get_payment_url(self, obj):
        if not obj.is_paid and obj.amount_due > 0:
            return self.context['request'].build_absolute_uri(
                f'/api/v1/payments/create/?invoice_id={obj.id}'
            )
        return None