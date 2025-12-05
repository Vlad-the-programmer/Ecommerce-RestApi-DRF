from django.conf import settings
from rest_framework import serializers

from common.models import ItemCommonModel
from common.utlis import send_email_confirmation
from .models import InternationalRate, ShippingClass
from .enums import ShippingType


class InternationalRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = InternationalRate
        fields = [
            'id', 'country', 'surcharge', 'date_created', 'date_updated',
            'is_active', 'is_deleted'
        ]
        read_only_fields = ['id', 'date_created', 'date_updated']

    def validate_surcharge(self, value):
        if value < 0:
            raise serializers.ValidationError("Surcharge cannot be negative.")
        return value


class ShippingClassSerializer(serializers.ModelSerializer):
    shipping_type_display = serializers.CharField(
        source='get_shipping_type_display', 
        read_only=True
    )
    carrier_type_display = serializers.CharField(
        source='get_carrier_type_display', 
        read_only=True
    )
    estimated_delivery = serializers.SerializerMethodField()
    total_delivery_time = serializers.SerializerMethodField()
    available_countries = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )

    class Meta:
        model = ShippingClass
        fields = [
            'id', 'name', 'shipping_notes', 'base_cost', 'shipping_type',
            'shipping_type_display', 'carrier_type', 'carrier_type_display',
            'estimated_days_min', 'estimated_days_max', 'cost_per_kg',
            'free_shipping_threshold', 'max_weight_kg', 'max_dimensions',
            'tracking_available', 'signature_required', 'insurance_included',
            'insurance_cost', 'domestic_only', 'available_countries',
            'handling_time_days', 'estimated_delivery', 'total_delivery_time',
            'date_created', 'date_updated', 'is_active', 'is_deleted'
        ]
        read_only_fields = ['id', 'date_created', 'date_updated']

    def get_estimated_delivery(self, obj):
        return obj.get_estimated_delivery()

    def get_total_delivery_time(self, obj):
        return obj.get_total_delivery_time()

    def validate(self, data):
        if 'estimated_days_min' in data and 'estimated_days_max' in data:
            if data['estimated_days_min'] > data['estimated_days_max']:
                raise serializers.ValidationError({
                    'estimated_days_max': 'Maximum days must be greater than or equal to minimum days.'
                })
        
        if 'free_shipping_threshold' in data and data['free_shipping_threshold'] is not None:
            if data['free_shipping_threshold'] < 0:
                raise serializers.ValidationError({
                    'free_shipping_threshold': 'Free shipping threshold cannot be negative.'
                })
        
        if data.get('shipping_type') == ShippingType.INTERNATIONAL and not data.get('available_countries'):
            raise serializers.ValidationError({
                'available_countries': 'Available countries must be specified for international shipping.'
            })
        
        return data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if 'available_countries' in representation and instance.available_countries:
            representation['available_countries'] = instance.available_countries
        return representation

    def to_internal_value(self, data):
        available_countries = data.pop('available_countries', None)
        internal_value = super().to_internal_value(data)
        if available_countries is not None:
            internal_value['available_countries'] = available_countries
        return internal_value

    def _get_order_items_display(self, shipping_class) -> list[ItemCommonModel]:
        """
        Format order items for display in the shipping email template.
        
        Args:
            shipping_class: The ShippingClass instance
            
        Returns:
            list: List of dictionaries containing item details
        """
        order_items = []
        
        for order in shipping_class.orders.all():
            for item in order.order_items.all():
                if hasattr(item, 'variant') and item.variant:
                    product_name = item.variant.display_name
                    sku = item.variant.sku
                else:
                    product_name = item.product.name
                    sku = item.product.sku
                
                price_per_item = float(item.total_price) / float(item.quantity) \
                                if item.quantity > 0 \
                                else 0
                
                order_items.append({
                    'name': product_name,
                    'sku': sku,
                    'quantity': item.quantity,
                    'price': f"{price_per_item:.2f}",
                    'total': f"{float(item.total_price):.2f}",
                    'image_url': item.product.images.first().image.url
                                if hasattr(item.product, 'images')
                                    and item.product.images.exists()
                                else None
                })
        
        return order_items

    def create(self, validated_data):
        shipping_class = ShippingClass.objects.create(**validated_data)

        context = {
            'customer_name': shipping_class.created_by.get_full_name()
                            if shipping_class.created_by
                            else 'Valued Customer',
            'order_number': f"SHIP-{shipping_class.id}",
            'tracking_number': shipping_class.tracking_number or 'Not available yet',
            'shipping_method': shipping_class.name,
            'estimated_delivery_date': shipping_class.get_estimated_delivery(),
            'carrier_name': shipping_class.get_carrier_type_display(),
            'tracking_url': shipping_class.get_tracking_url()
                            if hasattr(shipping_class, 'get_tracking_url')
                            else None,
            'shipping_address': {
                'name': shipping_class.recipient_name,
                'street1': shipping_class.address_line1,
                'street2': shipping_class.address_line2 or '',
                'city': shipping_class.city,
                'state': shipping_class.state,
                'zip_code': shipping_class.postal_code,
                'country': shipping_class.country.name,
                'country_code': shipping_class.country.code,
            },
            'order_items': self._get_order_items_display(shipping_class),
            'shipping_cost': shipping_class.get_shipping_total_cost(),
            'order_total': str(shipping_class.get_order_total()),
            'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@example.com'),
            'support_phone': getattr(settings, 'SUPPORT_PHONE', '+1 (555) 123-4567'),
            'site_name': getattr(settings, 'SITE_NAME', 'E-Commerce Site'),
            'site_url': getattr(settings, 'SITE_URL', 'https://your-ecommerce-site.com'),
        }

        send_email_confirmation(
            subject=f"Your Shipping Confirmation - Order #{context['order_number']}",
            template_name='shipping/emails/shipping_sent_confirm',
            context=context,
            to_emails=[shipping_class.customer_email]
                        if hasattr(shipping_class, 'customer_email')
                        else [],
        )

        return shipping_class
