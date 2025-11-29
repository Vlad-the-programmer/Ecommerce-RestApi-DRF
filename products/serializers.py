from rest_framework import serializers

from .enums import ProductType, ProductStatus, StockStatus, ProductLabel
from .models import  Product, ProductVariant, ProductImage, Location
from category.serializers import CategoryDetailSerializer


class LocationSerializer(serializers.ModelSerializer):
    """Serializer for Location model."""
    class Meta:
        model = Location
        fields = [
            'id', 'name', 'street', 'address_line_1',
            'address_line_2', 'house_number',
            'apartment_number','city', 'state',
            'zip_code', 'country', 'is_active', 'date_created', 'date_updated'
        ]
        read_only_fields = ['date_created', 'date_updated']


class ProductImageSerializer(serializers.ModelSerializer):
    """Serializer for ProductImage model."""
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        required=True,
    )
    image_url = serializers.SerializerMethodField()
    # thumbnail_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductImage
        fields = [
            'id', 'image', 'image_url', 'thumbnail_url', 'alt_text',
            'display_order', 'product_id', 'date_created', 'date_updated'
        ]
        read_only_fields = ['date_created', 'date_updated', 'image_url']
    
    def get_image_url(self, obj):
        if obj.image:
            return obj.image.url
        return None
    
    # def get_thumbnail_url(self, obj):
    #     if obj.image:
    #         # This assumes you have a thumbnail processor like sorl-thumbnail or easy-thumbnails
    #         # You may need to adjust this based on your thumbnail setup
    #         try:
    #             return obj.image['thumbnail'].url
    #         except:
    #             return obj.image.url
    #     return None


class ProductVariantSerializer(serializers.ModelSerializer):
    """Serializer for ProductVariant model."""
    in_stock = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    final_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        read_only=True
    )
    
    class Meta:
        model = ProductVariant
        fields = [
            'id', 'sku', 'color', 'size', 'material', 'style',
            'cost_price', 'price_adjustment', 'stock_quantity',
            'low_stock_threshold', 'in_stock', 'is_low_stock',
            'final_price', 'date_created', 'date_updated'
        ]
        read_only_fields = ['date_created', 'date_updated']
    
    def validate(self, data):
        """Validate that at least one variant attribute is provided."""
        if not any(field in data for field in ['color', 'size', 'material', 'style']):
            raise serializers.ValidationError(
                "At least one variant attribute (color, size, material, or style) must be provided."
            )
        return data


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product listings."""
    category = serializers.StringRelatedField()
    primary_image = serializers.SerializerMethodField()
    price_range = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    is_on_sale = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'product_name', 'slug', 'category', 'primary_image',
            'price', 'compare_at_price', 'price_range', 'in_stock',
            'is_on_sale', 'status', 'stock_status', 'label', 'date_created'
        ]
        read_only_fields = ['date_created']
    
    def get_primary_image(self, obj):
        primary_image = obj.product_images.filter(is_primary=True).first()
        if primary_image:
            return ProductImageSerializer(primary_image).data
        return None
    
    def get_price_range(self, obj):
        if obj.has_variants:
            return obj.get_variant_price_range()
        return {'min': obj.price, 'max': obj.price}


class ProductDetailSerializer(ProductListSerializer):
    """Detailed serializer for individual product view."""
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True, source='product_images')
    category_detail = CategoryDetailSerializer(source='category', read_only=True)
    subcategories = CategoryDetailSerializer(many=True, read_only=True)
    manufacturer_info = serializers.SerializerMethodField()
    
    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            'product_description', 'condition', 'variants', 'images',
            'weight', 'dimensions', 'requires_shipping', 'fragile',
            'hazardous', 'barcode', 'manufacturer_info', 'category_detail',
            'subcategories', 'product_type', 'sale_start_date', 'sale_end_date',
            'date_updated'
        ]
    
    def get_manufacturer_info(self, obj) -> dict:
        return {
            'manufacturing_location': obj.manufacturing_location,
            'manufacturing_date': obj.manufacturing_date,
            'batch_number': obj.batch_number,
            'shelf_life_days': obj.shelf_life.days if obj.shelf_life else None,
            'days_until_expiry': obj.days_until_expiry or None
        }


class DigitalProductSerializer(ProductDetailSerializer):
    """Serializer for digital products with additional digital-specific fields."""
    download_info = serializers.SerializerMethodField()
    
    class Meta(ProductDetailSerializer.Meta):
        fields = ProductDetailSerializer.Meta.fields + [
            'download_file', 'download_limit', 'access_duration',
            'file_size', 'file_type', 'download_info'
        ]
    
    def get_download_info(self, obj):
        if not obj.is_digital():
            return None
            
        return {
            'file_size_mb': round(obj.file_size / (1024 * 1024), 2) if obj.file_size else None,
            'file_type': obj.file_type,
            'download_limit': obj.download_limit,
            'access_duration_days': obj.access_duration.days if obj.access_duration else None
        }


class ServiceProductSerializer(ProductDetailSerializer):
    """Serializer for service products with service-specific fields."""
    service_info = serializers.SerializerMethodField()
    
    class Meta(ProductDetailSerializer.Meta):
        fields = ProductDetailSerializer.Meta.fields + [
            'service_type', 'duration', 'location_required',
            'location', 'provider_notes', 'service_info'
        ]
    
    def get_service_info(self, obj):
        if obj.product_type != ProductType.SERVICE:
            return None
            
        return {
            'service_type': obj.get_service_type_display(),
            'duration_minutes': obj.duration.total_seconds() // 60 if obj.duration else None,
            'location_required': obj.location_required,
            'location': LocationSerializer(obj.location).data if obj.location else None
        }


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating products."""
    variants = ProductVariantSerializer(many=True, required=False)
    images = ProductImageSerializer(many=True, required=False, source='product_images')
    
    class Meta:
        model = Product
        fields = [
            'product_name', 'product_description', 'category', 'subcategories',
            'price', 'compare_at_price', 'condition', 'status', 'stock_status',
            'label', 'track_inventory', 'low_stock_threshold', 'weight',
            'dimensions', 'requires_shipping', 'fragile', 'hazardous',
            'barcode', 'product_type', 'sale_start_date', 'sale_end_date',
            'manufacturing_location', 'manufacturing_date', 'batch_number',
            'shelf_life', 'variants', 'images'
        ]
    
    def create(self, validated_data):
        variants_data = validated_data.pop('variants', [])
        images_data = validated_data.pop('product_images', [])
        
        product = Product.objects.create(**validated_data)
        
        for variant_data in variants_data:
            ProductVariant.objects.create(product=product, **variant_data)
        
        for image_data in images_data:
            ProductImage.objects.create(product=product, **image_data)

        subcategories_data = validated_data.pop('subcategories', [])

        product = Product.objects.create(**validated_data)

        if subcategories_data:
            product.subcategories.set(subcategories_data)

        return product
    
    def update(self, instance, validated_data):
        variants_data = validated_data.pop('variants', None)
        images_data = validated_data.pop('product_images', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        if variants_data is not None:
            # Delete variants not in the request
            variant_ids = [v.get('id') for v in variants_data if 'id' in v]
            instance.product_variants.exclude(id__in=variant_ids).delete()
            
            for variant_data in variants_data:
                variant_id = variant_data.pop('id', None)
                if variant_id:
                    variant = instance.product_variants.filter(id=variant_id).first()
                    if variant:
                        for attr, value in variant_data.items():
                            setattr(variant, attr, value)
                        variant.save()
                else:
                    ProductVariant.objects.create(product=instance, **variant_data)
        
        if images_data is not None:
            # Delete images not in the request
            image_ids = [i.get('id') for i in images_data if 'id' in i]
            instance.product_images.exclude(id__in=image_ids).delete()
            
            for image_data in images_data:
                image_id = image_data.pop('id', None)
                if image_id:
                    image = instance.product_images.filter(id=image_id).first()
                    if image:
                        for attr, value in image_data.items():
                            setattr(image, attr, value)
                        image.save()
                else:
                    ProductImage.objects.create(product=instance, **image_data)
        
        return instance


class ProductBulkUpdateSerializer(serializers.Serializer):
    """Serializer for bulk updating products."""
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=100,
        help_text="List of product IDs to update"
    )
    
    status = serializers.ChoiceField(choices=ProductStatus.choices, required=False)
    stock_status = serializers.ChoiceField(choices=StockStatus.choices, required=False)
    label = serializers.ChoiceField(choices=ProductLabel.choices, required=False)
    track_inventory = serializers.BooleanField(required=False)
    
    def validate_ids(self, value):
        """Validate that all product IDs exist."""
        existing_ids = set(Product.objects.filter(id__in=value).values_list('id', flat=True))
        invalid_ids = set(value) - existing_ids
        
        if invalid_ids:
            raise serializers.ValidationError(
                f"The following product IDs do not exist: {', '.join(map(str, invalid_ids))}"
            )
        return value
    
    def update(self, instance, validated_data):
        ids = validated_data.pop('ids')
        update_fields = {k: v for k, v in validated_data.items() if v is not None}
        
        if update_fields:
            Product.objects.filter(id__in=ids).update(**update_fields)
        
        return Product.objects.filter(id__in=ids)
