from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path
from django import forms

from category.models import Category


class HasChildrenFilter(admin.SimpleListFilter):
    """Filter for categories that have children."""
    title = _('has children')
    parameter_name = 'has_children'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Yes')),
            ('no', _('No')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(children__isnull=False).distinct()
        if self.value() == 'no':
            return queryset.filter(children__isnull=True)
        return queryset


class HasProductsFilter(admin.SimpleListFilter):
    """Filter for categories that have products."""
    title = _('has products')
    parameter_name = 'has_products'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Yes')),
            ('no', _('No')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(products__isnull=False).distinct()
        if self.value() == 'no':
            return queryset.filter(products__isnull=True)
        return queryset


class CategoryTreeFilter(admin.SimpleListFilter):
    """Filter to show categories in a tree structure."""
    title = _('category tree')
    parameter_name = 'tree'

    def lookups(self, request, model_admin):
        return [('all', _('Show all (tree view)'))]

    def choices(self, changelist):
        yield {
            'selected': self.value() != 'all',
            'query_string': changelist.get_query_string(remove=[self.parameter_name]),
            'display': _('Flat view'),
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == lookup,
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }

    def queryset(self, request, queryset):
        # This filter is just for UI, doesn't filter the queryset
        return queryset


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    form = CategoryAdminForm
    list_display = (
        'name_with_tree', 'slug', 'parent_link', 'product_count',
        'subcategory_count', 'is_active', 'date_created'
    )
    list_filter = (
        'is_active', HasChildrenFilter, HasProductsFilter,
        'date_created', 'date_updated', CategoryTreeFilter
    )
    search_fields = ('name', 'slug', 'description')
    readonly_fields = (
        'slug', 'date_created', 'date_updated', 'date_deleted',
        'is_deleted', 'product_count', 'subcategory_count', 'full_path'
    )
    list_select_related = ('parent',)
    actions = [
        'make_active', 'make_inactive', 'rebuild_slugs',
        'export_selected_categories', 'delete_selected_categories'
    ]
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('name', 'slug', 'description', 'parent', 'full_path')
        }),
        (_('Status'), {
            'fields': ('is_active', 'is_deleted', 'date_deleted')
        }),
        (_('Statistics'), {
            'classes': ('collapse',),
            'fields': ('product_count', 'subcategory_count')
        }),
        (_('Timestamps'), {
            'classes': ('collapse',),
            'fields': ('date_created', 'date_updated')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _product_count=Count('products', distinct=True),
            _subcategory_count=Count('children', distinct=True)
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:category_id>/move/',
                self.admin_site.admin_view(self.move_category),
                name='category-move',
            ),
            path(
                'rebuild-tree/',
                self.admin_site.admin_view(self.rebuild_tree),
                name='category-rebuild-tree',
            ),
        ]
        return custom_urls + urls

    def name_with_tree(self, obj):
        """Display category name with indentation based on depth."""
        depth = 0
        parent = obj.parent
        while parent:
            depth += 1
            parent = parent.parent

        return format_html(
            '<span style="margin-left:{}px">{}</span>',
            depth * 20,  # 20px per level
            obj.name
        )

    name_with_tree.short_description = _('Name')
    name_with_tree.admin_order_field = 'name'

    def parent_link(self, obj):
        if obj.parent:
            url = reverse('admin:category_category_change', args=[obj.parent.id])
            return format_html('<a href="{}">{}</a>', url, obj.parent.name)
        return "-"

    parent_link.short_description = _('Parent')
    parent_link.admin_order_field = 'parent__name'

    def product_count(self, obj):
        if hasattr(obj, '_product_count'):
            return obj._product_count
        return obj.products.count()

    product_count.short_description = _('Products')
    product_count.admin_order_field = '_product_count'

    def subcategory_count(self, obj):
        if hasattr(obj, '_subcategory_count'):
            count = obj._subcategory_count
        else:
            count = obj.children.count()
        url = (
                reverse('admin:category_category_changelist') +
                f'?parent__id__exact={obj.id}'
        )
        return format_html('<a href="{}">{}</a>', url, count)

    subcategory_count.short_description = _('Subcategories')
    subcategory_count.admin_order_field = '_subcategory_count'

    @property
    def full_path(self, obj):
        return str(obj)

    full_path.short_description = _('Full Path')

    # Custom actions
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            _('Successfully activated %d categories.') % updated,
            messages.SUCCESS
        )

    make_active.short_description = _('Mark selected categories as active')

    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _('Successfully deactivated %d categories.') % updated,
            messages.SUCCESS
        )

    make_inactive.short_description = _('Mark selected categories as inactive')

    def rebuild_slugs(self, request, queryset):
        updated = 0
        for category in queryset:
            category.save(update_fields=['slug'])  # This will trigger slug rebuild
            updated += 1
        self.message_user(
            request,
            _('Successfully rebuilt slugs for %d categories.') % updated,
            messages.SUCCESS
        )

    rebuild_slugs.short_description = _('Rebuild slugs for selected categories')

    def delete_selected_categories(self, request, queryset):
        deleted = 0
        for category in queryset:
            can_delete, reason = category.can_be_deleted()
            if can_delete:
                category.delete()
                deleted += 1
            else:
                self.message_user(
                    request,
                    _('Could not delete %(name)s: %(reason)s') % {
                        'name': category.name,
                        'reason': reason
                    },
                    messages.WARNING
                )
        if deleted > 0:
            self.message_user(
                request,
                _('Successfully deleted %d categories.') % deleted,
                messages.SUCCESS
            )

    delete_selected_categories.short_description = _('Delete selected categories')

    def export_selected_categories(self, request, queryset):
        self.message_user(
            request,
            _('Export functionality would be implemented here for %d categories.') % queryset.count(),
            messages.INFO
        )

    export_selected_categories.short_description = _('Export selected categories')

    def move_category(self, request, category_id, *args, **kwargs):
        """Handle category movement in the tree."""
        self.message_user(request, _('Move category functionality would be implemented here.'))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    def rebuild_tree(self, request, *args, **kwargs):
        """Rebuild the entire category tree."""
        self.message_user(request, _('Rebuild tree functionality would be implemented here.'))
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

    def changelist_view(self, request, extra_context=None):
        """Override to handle tree view."""
        extra_context = extra_context or {}

        if request.GET.get('tree') == 'all':
            extra_context['categories'] = Category.objects.root_categories()
            return super().changelist_view(
                request,
                extra_context=extra_context,
                template_name='admin/category/category/tree_view.html'
            )

        return super().changelist_view(request, extra_context=extra_context)


class CategoryAdminForm(forms.ModelForm):
    """Custom form for Category admin with enhanced validation."""

    class Meta:
        model = Category
        fields = '__all__'

    def clean_parent(self):
        """Prevent circular references and other invalid parent assignments."""
        parent = self.cleaned_data.get('parent')
        instance = self.instance

        if instance.pk and parent and instance.pk == parent.pk:
            raise forms.ValidationError(_('A category cannot be its own parent.'))

        if parent and instance.pk:
            ancestors = set()
            current = parent
            while current:
                if current.pk == instance.pk:
                    raise forms.ValidationError(
                        _('This would create a circular reference in the category tree.')
                    )
                if current.pk in ancestors:
                    break
                ancestors.add(current.pk)
                current = current.parent

        return parent