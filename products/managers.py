import datetime
from django.utils import timezone
from django.db.models import Count, Q, Avg, Sum, F

from common.managers import SoftDeleteManager
from common.models import CommonModel
from products.enums import ProductStatus, StockStatus, ProductLabel


class ProductVariantManager(SoftDeleteManager):
    """
    Manager for size-color variant queries.
    """
    def get_queryset(self):
        return super().get_queryset().select_related('product')


class ProductManager(SoftDeleteManager):
    """
    Main product manager with common product queries.
    """
    def get_queryset(self):
        return super().get_queryset().filter(status=ProductStatus.PUBLISHED)
    
    def active(self):
        """Get only active products"""
        return self.filter(status=ProductStatus.PUBLISHED)
    
    def published(self):
        """Get only published products"""
        return self.filter(status=ProductStatus.PUBLISHED)

    def draft(self):
        """Get only draft products"""
        return self.filter(status=ProductStatus.DRAFT)

    def in_stock(self):
        """Get products that are in stock"""
        return self.filter(stock_status=StockStatus.IN_STOCK)

    def out_of_stock(self):
        """Get products that are out of stock"""
        return self.filter(stock_status=StockStatus.OUT_OF_STOCK)

    def on_sale(self):
        """Get products currently on sale"""
        now = timezone.now()
        return self.filter(
            compare_at_price__gt=F('price'),
            sale_start_date__lte=now,
            sale_end_date__gte=now
        )

    def featured(self):
        """Get currently featured products"""
        now = timezone.now()
        return self.filter(
            Q(label=ProductLabel.FEATURED) |
            Q(featured_until__gte=now)
        )

    def new_arrivals(self, days=30):
        """Get products added in the last N days"""
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return self.filter(
            date_created__gte=cutoff_date,
            label=ProductLabel.NEW_ARRIVAL
        )

    def low_stock(self):
        """Get products with low stock levels"""
        return self.filter(
            stock_quantity__lte=F('low_stock_threshold'),
            stock_status=StockStatus.IN_STOCK
        )

    def by_category(self, category):
        """Get products by category (can accept category object or ID)"""
        if isinstance(category, CommonModel):
            return self.filter(category=category)
        return self.filter(category_id=category)

    def with_positive_margin(self):
        """Get products with positive profit margin"""
        return self.filter(
            cost_price__isnull=False,
            price__gt=F('cost_price')
        )

    def search(self, query):
        """Basic search across product name and description"""
        return self.filter(
            Q(product_name__icontains=query) |
            Q(product_description__icontains=query)
        )


class ProductReportManager(SoftDeleteManager):
    """
    Manager for product analytics and reporting.
    """
    def sales_performance(self):
        """Get products with sales performance data"""
        # This would join with order data in a real implementation
        return self.annotate(
            total_sold=Count('order_items'),
            average_rating=Avg('reviews__rating')
        )

    def profit_analysis(self):
        """Get products with profit analysis"""
        return self.filter(
            cost_price__isnull=False
        ).annotate(
            profit_margin=(
                (F('price') - F('cost_price')) /
                F('price') * 100
            )
        )

    def inventory_value(self):
        """Calculate total inventory value"""
        from django.db.models import DecimalField
        return self.aggregate(
            total_value=Sum(
                F('cost_price') * F('stock_quantity'),
                output_field=DecimalField()
            )
        )


class ProductAdminManager(SoftDeleteManager):
    """
    Manager for admin-specific product queries.
    """
    def needs_attention(self):
        """Get products that need admin attention"""
        return self.filter(
            Q(stock_quantity=0) |
            Q(stock_quantity__lte=F('low_stock_threshold')) |
            Q(status=ProductStatus.DRAFT) |
            Q(cost_price__isnull=True)
        )

    def without_images(self):
        """Get products without images"""
        # Assuming you have an Image model related to Product
        return self.annotate(
            image_count=Count('images')
        ).filter(image_count=0)

    def recently_updated(self, hours=24):
        """Get products updated in the last N hours"""
        cutoff = timezone.now() - datetime.timedelta(hours=hours)
        return self.filter(date_updated__gte=cutoff)