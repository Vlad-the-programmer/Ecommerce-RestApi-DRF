from datetime import timedelta

from django.db.models import Count, Q, Prefetch
from django.utils import timezone
from common.managers import SoftDeleteManager


class WishListManager(SoftDeleteManager):
    """
    Custom manager for Wishlist model with wishlist-specific methods.
    """

    def for_user(self, user):
        """Get wishlist for specific user"""
        return self.get_queryset().filter(user=user).first()

    def public_wishlists(self):
        """Get all public wishlists"""
        return self.get_queryset().filter(is_public=True)

    def with_items_count(self):
        """Annotate wishlists with items count"""
        return self.get_queryset().annotate(
            items_count=Count('wishlist_items', filter=Q(wishlist_items__is_deleted=False))
        )

    def with_items(self):
        """Prefetch wishlist items for performance"""
        from .models import WishListItem
        return self.get_queryset().prefetch_related(
            Prefetch(
                'wishlist_items',
                queryset=WishListItem.objects.select_related('product', 'variant')
            )
        )

    def get_or_create_for_user(self, user, name="My Wishlist", is_public=False):
        """
        Get or create wishlist for user with proper validation.
        Returns (wishlist, created) tuple.
        """
        wishlist = self.for_user(user)
        created = False

        if not wishlist:
            wishlist = self.model(
                user=user,
                name=name,
                is_public=is_public
            )
            wishlist.full_clean()  # Run validation
            wishlist.save()
            created = True

        return wishlist, created

    def user_has_wishlist(self, user):
        """Check if user has an active wishlist"""
        return self.get_queryset().filter(user=user).exists()


class WishListItemManager(SoftDeleteManager):
    """
    Custom manager for WishListItem model with item-specific methods.
    """

    def for_wishlist(self, wishlist_id):
        """Get all items for specific wishlist"""
        return self.get_queryset().filter(wishlist_id=wishlist_id)

    def for_user(self, user_id):
        """Get all wishlist items for specific user"""
        return self.get_queryset().filter(user_id=user_id)

    def for_product(self, product_id):
        """Get all wishlist items for specific product"""
        return self.get_queryset().filter(product_id=product_id)

    def for_variant(self, variant_id):
        """Get all wishlist items for specific variant"""
        return self.get_queryset().filter(variant_id=variant_id)

    def high_priority(self):
        """Get high priority wishlist items"""
        from .models import WishListItemPriority
        return self.get_queryset().filter(priority=WishListItemPriority.HIGH)

    def with_product_details(self):
        """Select related product and variant details"""
        return self.get_queryset().select_related('product', 'variant')

    def available_items(self):
        """Get wishlist items for available products/variants"""
        from products.enums import StockStatus
        return self.get_queryset().filter(
            Q(product__stock_status=StockStatus.IN_STOCK) |
            Q(variant__is_in_stock=True)
        )

    def unavailable_items(self):
        """Get wishlist items for unavailable products/variants"""
        from products.enums import StockStatus
        return self.get_queryset().filter(
            Q(product__stock_status=StockStatus.OUT_OF_STOCK) |
            Q(variant__is_in_stock=False)
        ).exclude(
            Q(product__stock_status=StockStatus.IN_STOCK) |
            Q(variant__is_in_stock=True)
        )

    def by_priority(self):
        """Order items by priority (highest first)"""
        return self.get_queryset().order_by('-priority', 'date_created')

    def recently_added(self, days=30):
        """Get items added in the last specified days"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.get_queryset().filter(date_created__gte=cutoff_date)

    def get_user_wishlist_items(self, user_id, wishlist_id=None):
        """
        Get wishlist items for user, optionally filtered by specific wishlist.
        """
        queryset = self.for_user(user_id)
        if wishlist_id:
            queryset = queryset.filter(wishlist_id=wishlist_id)
        return queryset

    def move_items_to_cart(self, wishlist_item_ids, cart):
        """
        Move multiple wishlist items to cart and delete them from wishlist.
        Returns list of created/updated cart items.
        """
        items = self.get_queryset().filter(id__in=wishlist_item_ids)
        cart_items = []

        for wishlist_item in items:
            cart_item = wishlist_item.move_to_cart(cart)
            cart_items.append(cart_item)

        return cart_items

    def bulk_update_priority(self, wishlist_item_ids, new_priority):
        """Bulk update priority for multiple wishlist items"""
        return self.get_queryset().filter(id__in=wishlist_item_ids).update(
            priority=new_priority,
            date_updated=timezone.now()
        )