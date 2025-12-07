from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import Refund, RefundItem
from .enums import RefundStatus, RefundReason
from orders.models import Order
from payments.models import Payment


class RefundItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefundItem
        fields = [
            'id', 'order_item', 'quantity', 'unit_price', 'reason',
            'date_created', 'date_updated'
        ]
        read_only_fields = ['id', 'date_created', 'date_updated', 'unit_price']


class RefundSerializer(serializers.ModelSerializer):
    items = RefundItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)
    user = serializers.StringRelatedField()
    order = serializers.StringRelatedField()
    payment = serializers.StringRelatedField()

    class Meta:
        model = Refund
        fields = [
            'id', 'order', 'payment', 'user', 'amount_requested', 'currency', 'reason',
            'reason_display', 'status', 'status_display', 'customer_notes', 'rejection_reason',
            'date_created', 'processed_at', 'date_completed', 'items'
        ]
        read_only_fields = [
            'id', 'status', 'status_display', 'date_created', 'processed_at',
            'date_completed', 'amount_requested', 'currency', 'user'
        ]


class RefundCreateSerializer(serializers.ModelSerializer):
    order = serializers.PrimaryKeyRelatedField(
        queryset=Order.objects.all(),
        required=True
    )
    payment = serializers.PrimaryKeyRelatedField(
        queryset=Payment.objects.all(),
        required=False
    )
    items = RefundItemSerializer(many=True, required=True)
    reason = serializers.ChoiceField(choices=RefundReason.choices)

    class Meta:
        model = Refund
        fields = ['order', 'payment', 'reason', 'customer_notes', 'items']

    def validate(self, data):
        order = data['order']
        user = self.context['request'].user

        if order.user != user:
            raise ValidationError({'order': 'You can only request refunds for your own orders.'})

        if not order.can_be_refunded():
            raise ValidationError({'order': 'This order is not eligible for a refund.'})

        items = data.get('items', [])
        if not items:
            raise ValidationError({'items': 'At least one item is required for a refund.'})

        if Refund.objects.filter(order=order, status=RefundStatus.PENDING).exists():
            raise ValidationError({'order': 'A refund request is already pending for this order.'})

        return data

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        order = validated_data['order']

        refund = Refund.objects.create(
            user=self.context['request'].user,
            order=order,
            payment=validated_data.get('payment'),
            reason=validated_data['reason'],
            notes=validated_data.get('notes', ''),
            currency=order.currency,
            amount=0  # Will be updated after items are created
        )

        refund_items = [
            RefundItem(refund=refund, **item_data)
            for item_data in items_data
        ]
        RefundItem.objects.bulk_create(refund_items)
        
        refund.update_amounts()

        # refund.send_creation_notification()

        return refund


class RefundUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = ['customer_notes', 'rejection_reason', 'amount_refunded',
                  'amount_approved', 'status', 'processed_at', 'date_completed',
                  'processed_by', 'refund_receipt', 'internal_notes', 'reason_description',
                  ]
        extra_kwargs = {
            'customer_notes': {'required': False},
            'rejection_reason': {'required': False}
        }