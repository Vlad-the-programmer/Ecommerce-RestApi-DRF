from common.managers import NonDeletedObjectsManager


class ShippingClassManager(NonDeletedObjectsManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True, order__is_active=True)