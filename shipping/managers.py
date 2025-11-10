from common.managers import SoftDeleteManager


class ShippingClassManager(SoftDeleteManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

    def active(self):
        """Get active shipping classes"""
        return self.get_queryset().filter(is_active=True)

    def by_type(self, shipping_type):
        """Get shipping classes by type"""
        return self.get_queryset().filter(shipping_type=shipping_type)

    def domestic(self):
        """Get domestic shipping classes"""
        return self.get_queryset().filter(domestic_only=True)

    def international(self):
        """Get international shipping classes"""
        return self.get_queryset().filter(domestic_only=False)

    def with_free_shipping(self):
        """Get shipping classes that offer free shipping"""
        return self.get_queryset().filter(free_shipping_threshold__isnull=False)