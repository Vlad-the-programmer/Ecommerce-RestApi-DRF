from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from orders.enums import OrderStatuses
from orders.models import Order, OrderItem, OrderTax, OrderStatusHistory
from products.serializers import ProductVariantSerializer


class OrderTaxSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderTax
        fields = [
            'id', 'name', 'rate', 'amount', 'tax_value', 'amount_with_taxes',
            'date_created', 'date_updated'
        ]
        read_only_fields = ['id', 'date_created', 'date_updated']


class OrderItemSerializer(serializers.ModelSerializer):
    variant_details = ProductVariantSerializer(source='variant', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'variant', 'variant_details', 'quantity', 
            'total_price', 'date_created', 'date_updated'
        ]
        read_only_fields = ['id', 'total_price', 'date_created', 'date_updated']


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    changed_by_username = serializers.CharField(source='changed_by.username', read_only=True)
    
    class Meta:
        model = OrderStatusHistory
        fields = [
            'id', 'status', 'status_display', 'notes', 'changed_by', 
            'changed_by_username', 'date_created'
        ]
        read_only_fields = ['id', 'status_display', 'date_created']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    taxes = OrderTaxSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items_count = serializers.IntegerField(source='get_items_count', read_only=True)
    can_be_cancelled = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'user', 'cart', 'status', 'status_display', 
            'status_history', 'total_amount', 'shipping_class', 'shipping_address',
            'items', 'taxes', 'items_count', 'can_be_cancelled',
            'date_created', 'date_updated'
        ]
        read_only_fields = [
            'id', 'order_number', 'status_display', 'status_history', 'total_amount',
            'items_count', 'can_be_cancelled', 'date_created', 'date_updated'
        ]
    
    def validate(self, data):
        if self.instance and self.instance.status != 'pending':
            restricted_fields = ['shipping_class', 'shipping_address']
            for field in restricted_fields:
                if field in data and data[field] != getattr(self.instance, field):
                    raise ValidationError({
                        field: _(f"Cannot update {field} after order is placed.")
                    })
        return data


class CreateOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['shipping_class', 'shipping_address']
        
    def create(self, validated_data):
        user = self.context['request'].user
        cart = user.cart
        
        if not cart or not cart.items.exists():
            raise ValidationError({"cart": _("Cannot create order with an empty cart")})
            
        order = Order.objects.create(
            user=user,
            cart=cart,
            shipping_class=validated_data.get('shipping_class'),
            shipping_address=validated_data.get('shipping_address'),
            status=OrderStatuses.PENDING
        )

        to_create = []
        for cart_item in cart.items.all():
            to_create.append(
                OrderItem(
                    order=order,
                    product=cart_item.product,
                    variant=cart_item.variant,
                    quantity=cart_item.quantity,
                    total_price=cart_item.total_price
                )
            )

        OrderItem.objects.bulk_create(to_create)

        order.total_amount = order.get_order_total_amount()
        order.save()
        
        return order
