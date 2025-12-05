from rest_framework import serializers
from payments.models import Payment
from payments.enums import PaymentMethod, PaymentStatus


class PaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id',
            'invoice',
            'user',
            'payment_reference',
            'amount',
            'currency',
            'method',
            'method_display',
            'status',
            'status_display',
            'transaction_date',
            'confirmed_at',
            'notes',
            'date_created',
            'date_updated',
        ]
        read_only_fields = [
            'id',
            'date_created',
            'date_updated',
            'method_display',
            'status_display',
            'transaction_date',
        ]

    def validate_method(self, value):
        if value not in dict(PaymentMethod.choices):
            raise serializers.ValidationError("Invalid payment method.")
        return value

    def validate_status(self, value):
        if value not in dict(PaymentStatus.choices):
            raise serializers.ValidationError("Invalid payment status.")
        return value


class PaymentCreateSerializer(PaymentSerializer):
    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + ['notes']
        read_only_fields = [f for f in PaymentSerializer.Meta.read_only_fields if f != 'transaction_date']


class PaymentUpdateSerializer(PaymentSerializer):
    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields
        read_only_fields = PaymentSerializer.Meta.read_only_fields + [
            'invoice',
            'user',
            'payment_reference',
            'amount',
            'currency',
            'method',
        ]
