# Third-party
from django_countries.serializer_fields import CountryField

from dj_rest_auth.serializers import UserDetailsSerializer as DefaultUserDetailsSerializer
from userAuth.serializers import UserSerializer


class CustomUserDetailsSerializer(DefaultUserDetailsSerializer):
    """Custom user details serializer."""
    country = CountryField()
    user = UserSerializer(read_only=True)

    class Meta(DefaultUserDetailsSerializer.Meta):
        fields = ('pk', 'email', 'first_name', 'last_name', 'gender',
                  'country', 'user', 'is_active', 'date_joined')
        read_only_fields = ('email', 'is_active', 'date_joined')

