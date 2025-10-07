# Third-party
from django_countries.serializer_fields import CountryField

# DRF
from rest_framework import serializers

from dj_rest_auth.serializers import UserDetailsSerializer as DefaultUserDetailsSerializer



class CustomUserDetailsSerializer(DefaultUserDetailsSerializer):
    """Custom user details serializer."""
    gender = serializers.CharField(source='get_gender_display')
    country = CountryField()
    
    class Meta(DefaultUserDetailsSerializer.Meta):
        fields = ('pk', 'email', 'first_name', 'last_name', 'gender', 'country', 'is_active', 'date_joined')
        read_only_fields = ('email', 'is_active', 'date_joined')

