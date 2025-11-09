from common.managers import SoftDeleteManger


class ShippingClassManager(SoftDeleteManger):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True, order__is_active=True)