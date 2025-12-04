from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import Review


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['id', 'product', 'rating', 'title', 'content']
        read_only_fields = ['id', 'user']
        extra_kwargs = {
            'rating': {'required': True, 'min_value': 0, 'max_value': 5},
            'content': {'required': False, 'allow_blank': True},
            'title': {'required': False, 'allow_blank': True, 'max_length': 255}
        }

    def validate_rating(self, value):
        """Ensure rating is between 0 and 5 with up to 2 decimal places."""
        if not (0 <= value <= 5):
            raise serializers.ValidationError(_("Rating must be between 0 and 5."))
        return round(float(value), 2)

    def validate_product(self, value):
        """Ensure product exists and is not deleted."""
        if value.is_deleted:
            raise serializers.ValidationError(_("Cannot review a deleted product."))
        return value


class ReviewUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['rating', 'title', 'content', 'is_active']
        extra_kwargs = {
            'rating': {'required': False, 'min_value': 0, 'max_value': 5},
            'content': {'required': False, 'allow_blank': True},
            'title': {'required': False, 'allow_blank': True, 'max_length': 255},
            'is_active': {'required': False}
        }

    def validate_rating(self, value):
        """Ensure rating is between 0 and 5 with up to 2 decimal places."""
        if value is not None and not (0 <= value <= 5):
            raise serializers.ValidationError(_("Rating must be between 0 and 5."))
        return round(float(value), 2) if value is not None else None


class ReviewListSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    product = serializers.StringRelatedField()
    rating_stars = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            'id', 'user', 'product', 'rating', 'rating_stars',
            'title', 'content', 'date_created', 'date_updated'
        ]
        read_only_fields = fields

    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'email': obj.user.email
        }

    def get_rating_stars(self, obj):
        return obj.rating_in_stars()