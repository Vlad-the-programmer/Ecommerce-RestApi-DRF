from django.db import models
from django.utils.translation import gettext_lazy as _


class ProductCondition(models.TextChoices):
    NEW = 'new', _('New')
    USED = 'used', _('Used')
    REFURBISHED = 'refurbished', _('Refurbished')
    OPEN_BOX = 'open_box', _('Open Box')
    DAMAGED = 'damaged', _('Damaged')


class ProductStatus(models.TextChoices):
    DRAFT = 'draft', _('Draft')
    PUBLISHED = 'published', _('Published')
    ARCHIVED = 'archived', _('Archived')
    DELETED = 'deleted', _('Deleted')


class StockStatus(models.TextChoices):
    IN_STOCK = 'in_stock', _('In Stock')
    OUT_OF_STOCK = 'out_of_stock', _('Out of Stock')
    BACKORDER = 'backorder', _('Backorder')
    DISCONTINUED = 'discontinued', _('Discontinued')
    PRE_ORDER = 'pre_order', _('Pre-Order')


class ProductLabel(models.TextChoices):
    NONE = 'none', _('None')
    HOT = 'hot', _('Hot')
    SALE = 'sale', _('Sale')
    NEW_ARRIVAL = 'new_arrival', _('New Arrival')
    FEATURED = 'featured', _('Featured')
    BEST_SELLER = 'best_seller', _('Best Seller')
    LIMITED_EDITION = 'limited_edition', _('Limited Edition')
    CLEARANCE = 'clearance', _('Clearance')


class ProductType(models.TextChoices):
    PHYSICAL = 'physical', _('Physical Product')
    DIGITAL = 'digital', _('Digital Product')
    SERVICE = 'service', _('Service')
    BUNDLE = 'bundle', _('Product Bundle')
    SUBSCRIPTION = 'subscription', _('Subscription')


class ServiceType(models.TextChoices):
    CONSULTATION = 'consultation', _('Consultation')
    REPAIR = 'repair', _('Repair')
    INSTALLATION = 'installation', _('Installation')
    TRAINING = 'training', _('Training')
    OTHER = 'other', _('Other')