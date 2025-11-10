from django.db import models


class CategoryManager(models.Manager):
    """
    Simple manager for Category model with soft deletion support.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def root_categories(self):
        """Get all root categories (no parent)"""
        return self.get_queryset().filter(parent__isnull=True)

    def subcategories(self):
        """Get all subcategories (have parent)"""
        return self.get_queryset().filter(parent__isnull=False)

    def children_of(self, category):
        """Get direct children of a category"""
        return self.get_queryset().filter(parent=category)

    def by_slug(self, slug):
        """Get category by slug"""
        return self.get_queryset().filter(slug=slug).first()