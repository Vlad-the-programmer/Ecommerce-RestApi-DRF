from django.utils.translation import gettext_lazy as _
from django.db import models


class Gender(models.TextChoices):
    MALE = "male", _("Male")
    FEMALE = "female", _("Female")
    OTHER = "other", _("Other")
    NOT_SPECIFIED = "not_specified", _("Not Specified")


class UserRole(models.TextChoices):
    SUPER_ADMIN = "super_admin", _("Super Admin")
    MANAGER = "manager", _("Manager")
    EMPLOYEE = "employee", _("Employee")
    CUSTOMER = "customer", _("Customer")
    VENDOR = "vendor", _("Vendor")


user_roles_descriptions = {
    UserRole.SUPER_ADMIN: _("Super Admin is the highest level of access and can perform all actions in the system"),
    UserRole.MANAGER: _("Manager is the second highest level of access and can perform all actions in the system"),
    UserRole.EMPLOYEE: _("Employee works in a store and can perform specific actions."),
    UserRole.CUSTOMER: _("Customer is a consumer of products in the online store"),
    UserRole.VENDOR: _("Vendor is a supplier of products in the online store"),
}