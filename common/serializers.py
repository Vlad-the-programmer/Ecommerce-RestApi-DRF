from rest_framework import serializers

class BaseCustomModelSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ['uuid', 'date_created', 'date_updated', 'is_deleted', 'is_active']
        read_only_fields = ['uuid', 'date_created', 'date_updated', 'is_deleted', 'is_active']

