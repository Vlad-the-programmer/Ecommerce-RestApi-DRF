from django.db import models
from django.db.models import Avg, Count

from common.managers import SoftDeleteManager


class ReviewManager(SoftDeleteManager):
    """
    Simple manager for Review model with soft deletion support.
    """

    def for_product(self, product):
        """Get all reviews for a specific product"""
        return self.get_queryset().filter(product=product)

    def for_user(self, user):
        """Get all reviews by a specific user"""
        return self.get_queryset().filter(user=user)

    def high_rated(self, min_rating=4.0):
        """Get highly rated reviews"""
        return self.get_queryset().filter(rating__gte=min_rating)

    def low_rated(self, max_rating=2.0):
        """Get low rated reviews"""
        return self.get_queryset().filter(rating__lte=max_rating)

    def with_rating_stats(self):
        """Annotate with rating statistics"""
        return self.get_queryset().aggregate(
            avg_rating=Avg('rating'),
            total_reviews=Count('id')
        )