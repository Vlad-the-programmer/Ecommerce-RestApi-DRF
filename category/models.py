from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError

from category.managers import CategoryManager
from common.models import SlugFieldCommonModel


class Category(SlugFieldCommonModel):
    """
    Category model with parent-child hierarchy.
    Supports main categories and nested subcategories.
    """
    slug_fields = ["parent__name", "name"]
    objects = CategoryManager()

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Category Name"),
        help_text=_("Name of the category")
    )
    slug = models.SlugField(
        max_length=150,
        unique=True,
        blank=True,
        verbose_name=_("URL Slug"),
        help_text=_("Unique URL-friendly identifier")
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Parent Category"),
        help_text=_("Parent category for nested subcategories")
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Optional category description")
    )

    class Meta:
        db_table = "categories"
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
        ordering = ["name"]
        indexes = [
            models.Index(fields=['parent']),
            models.Index(fields=['slug'], name='category_slug_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['parent', 'name'],
                name='unique_category_name',
                condition=models.Q(is_deleted=False)  # Only enforce for active categories
            ),
            models.CheckConstraint(
                check=~models.Q(pk=models.F('parent_id')),
                name='prevent_self_parent_reference_for_category'
            ),
        ]


    def __str__(self):
        full_path = [self.name]
        parent = self.parent
        while parent:
            full_path.insert(0, parent.name)
            parent = parent.parent
        return " > ".join(full_path)

    @property
    def full_name_for_slug(self):
        parts = [self.name]
        parent = self.parent
        while parent:
            parts.insert(0, parent.name)
            parent = parent.parent
        return "-".join(parts)

    def clean(self):
        """Validate category before saving"""
        super().clean()

        # Prevent setting deleted category as parent
        if self.parent and self.parent.is_deleted:
            raise ValidationError(_("Cannot set deleted category as parent"))

        # Prevent circular references
        if self.parent and self.parent == self:
            raise ValidationError(_("Category cannot be its own parent"))

    @property
    def is_root(self):
        """Check if this is a root category"""
        return self.parent is None

    @property
    def is_subcategory(self):
        """Check if this is a subcategory"""
        return self.parent is not None
