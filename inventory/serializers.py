from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from common.models import CommonModel
from inventory.models import WarehouseProfile, Inventory
from inventory.enums import WAREHOUSE_TYPE


class WarehouseSerializer(serializers.ModelSerializer):
    warehouse_type_display = serializers.CharField(
        source='get_warehouse_type_display',
        read_only=True
    )
    
    class Meta:
        model = WarehouseProfile
        fields = [
            'id', 'uuid', 'name', 'code', 'warehouse_type', 'warehouse_type_display',
            'is_operational', 'is_active_fulfillment', 'capacity', 'current_utilization',
            'contact_phone', 'contact_email', 'address_line_1', 'address_line_2',
            'city', 'state', 'zip_code', 'country', 'country_code', 'sla_days',
            'is_express_available', 'max_order_per_day', 'timezone', 'date_created',
            'date_updated'
        ]
        read_only_fields = ['id', 'uuid', 'date_created', 'date_updated', 'current_utilization']

    def validate_capacity(self, value):
        if value <= 0:
            raise ValidationError(_("Capacity must be greater than 0"))
        return value

    def validate(self, data):
        instance = getattr(self, 'instance', None)
        if instance and 'capacity' in data and instance.current_utilization > data['capacity']:
            raise ValidationError({
                'capacity': _("New capacity cannot be less than current utilization")
            })
        return data


class InventorySerializer(serializers.ModelSerializer):
    product_variant_name = serializers.CharField(
        source='product_variant.name',
        read_only=True
    )
    warehouse_name = serializers.CharField(
        source='warehouse.name',
        read_only=True
    )
    
    class Meta:
        model = Inventory
        fields = [
            'id', 'uuid', 'product_variant', 'product_variant_name', 'warehouse',
            'warehouse_name', 'quantity_available', 'quantity_reserved',
            'reorder_level', 'is_backorder_allowed', 'cost_price', 'batch_number',
            'expiry_date', 'last_restocked', 'last_checked', 'date_created',
            'date_updated', 'manufacturing_cost_adjustment', 'packaging_cost_adjustment',
            'shipping_cost_adjustment', 'total_landed_cost', 'inventory_value'
        ]
        read_only_fields = [
            'id', 'uuid', 'date_created', 'date_updated', 'last_checked',
            'total_landed_cost', 'inventory_value'
        ]

    def validate_quantity_available(self, value):
        if value < 0:
            raise ValidationError(_("Available quantity cannot be negative"))
        return value

    def validate_quantity_reserved(self, value):
        if value < 0:
            raise ValidationError(_("Reserved quantity cannot be negative"))
        return value

    def validate(self, data):
        instance = getattr(self, 'instance', None)
        
        if 'quantity_reserved' in data or 'quantity_available' in data:
            reserved = data.get('quantity_reserved', getattr(instance, 'quantity_reserved', 0))
            available = data.get('quantity_available', getattr(instance, 'quantity_available', 0))
            
            if reserved > available:
                raise ValidationError({
                    'quantity_reserved': _("Reserved quantity cannot exceed available quantity")
                })
        
        if not instance and 'product_variant' not in data:
            raise ValidationError({
                'product_variant': _("Product variant is required")
            })
            
        if not instance and 'warehouse' not in data:
            raise ValidationError({
                'warehouse': _("Warehouse is required")
            })
            
        return data


class InventoryUpdateSerializer(serializers.ModelSerializer):
    """
    Specialized serializer for inventory updates that doesn't require all fields
    and handles stock adjustments safely.
    """
    adjustment = serializers.IntegerField(
        required=False,
        help_text=_("Positive or negative number to adjust inventory by")
    )
    
    class Meta:
        model = Inventory
        fields = [
            'quantity_available', 'quantity_reserved', 'reorder_level',
            'is_backorder_allowed', 'cost_price', 'batch_number', 'expiry_date',
            'adjustment', 'manufacturing_cost_adjustment', 'packaging_cost_adjustment',
            'shipping_cost_adjustment'
        ]
        read_only_fields = ['last_checked']

    def validate_adjustment(self, value):
        if value == 0:
            raise ValidationError(_("Adjustment cannot be zero"))
        return value

    def update(self, instance, validated_data):
        adjustment = validated_data.pop('adjustment', None)
        if adjustment is not None:
            new_quantity = instance.quantity_available + adjustment
            if new_quantity < 0:
                raise ValidationError({
                    'adjustment': _("Resulting quantity cannot be negative")
                })
            validated_data['quantity_available'] = new_quantity
            
        return super().update(instance, validated_data)
