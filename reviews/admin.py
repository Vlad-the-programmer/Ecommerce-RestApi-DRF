from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Avg, Q

from .models import Review


class RatingFilter(admin.SimpleListFilter):
    """Filter reviews by rating range."""
    title = _('rating')
    parameter_name = 'rating_range'

    def lookups(self, request, model_admin):
        return (
            ('5', _('5 stars')),
            ('4', _('4+ stars')),
            ('3', _('3+ stars')),
            ('2', _('2+ stars')),
            ('1', _('1+ stars')),
            ('0', _('Unrated')),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == '5':
            return queryset.filter(rating=5)
        elif value == '4':
            return queryset.filter(rating__gte=4)
        elif value == '3':
            return queryset.filter(rating__gte=3)
        elif value == '2':
            return queryset.filter(rating__gte=2)
        elif value == '1':
            return queryset.filter(rating__gte=1)
        elif value == '0':
            return queryset.filter(rating__isnull=True)
        return queryset


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Admin configuration for Review model."""
    list_display = (
        'id', 'product_link', 'user_link', 'rating_stars', 'short_content',
        'is_active', 'date_created', 'admin_actions'
    )
    list_display_links = ('id', 'rating_stars')
    list_filter = (RatingFilter, 'is_active', 'date_created')
    search_fields = (
        'user__email', 'user__first_name', 'user__last_name',
        'product__name', 'title', 'content'
    )
    readonly_fields = (
        'date_created', 'date_updated', 'short_content', 'rating_stars',
        'product_link', 'user_link'
    )
    list_select_related = ('user', 'product')
    actions = ['activate_reviews', 'deactivate_reviews', 'delete_selected']
    fieldsets = (
        (None, {
            'fields': ('user_link', 'product_link', 'rating', 'title', 'content')
        }),
        (_('Status'), {
            'fields': ('is_active', 'is_deleted'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('date_created', 'date_updated'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'product')

    def product_link(self, obj):
        if obj.product:
            url = reverse('admin:products_product_change', args=[obj.product.id])
            return format_html('<a href="{}">{}</a>', url, str(obj.product))
        return "-"
    product_link.short_description = _('Product')
    product_link.admin_order_field = 'product__name'

    def user_link(self, obj):
        if obj.user:
            url = reverse('admin:users_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.get_full_name() or obj.user.email)
        return _("Anonymous")
    user_link.short_description = _('User')
    user_link.admin_order_field = 'user__email'

    def rating_stars(self, obj):
        if obj.rating is not None:
            stars = '★' * int(round(obj.rating)) + '☆' * (5 - int(round(obj.rating)))
            return f"{stars} ({obj.rating:.1f}/5)"
        return _("No rating")
    rating_stars.short_description = _('Rating')
    rating_stars.admin_order_field = 'rating'

    def short_content(self, obj):
        if obj.content:
            content = obj.content.strip()
            return (content[:75] + "...") if len(content) > 75 else content
        return "-"
    short_content.short_description = _('Content Preview')

    def admin_actions(self, obj):
        """Custom actions column with buttons."""
        buttons = []
        change_url = reverse('admin:reviews_review_change', args=[obj.id])
        buttons.append(f'<a href="{change_url}" class="button">{_("Edit")}</a>')
        
        if obj.is_active:
            deactivate_url = reverse('admin:reviews_review_deactivate', args=[obj.id])
            buttons.append(f'<a href="{deactivate_url}" class="button">{_("Deactivate")}</a>')
        else:
            activate_url = reverse('admin:reviews_review_activate', args=[obj.id])
            buttons.append(f'<a href="{activate_url}" class="button">{_("Activate")}</a>')
        
        return format_html(' '.join(buttons))
    admin_actions.short_description = _('Actions')
    admin_actions.allow_tags = True

    def activate_reviews(self, request, queryset):
        """Admin action to activate selected reviews."""
        updated = queryset.update(is_active=True)
        self.message_user(request, _("Successfully activated %(count)d reviews.") % {'count': updated})
    activate_reviews.short_description = _("Activate selected reviews")

    def deactivate_reviews(self, request, queryset):
        """Admin action to deactivate selected reviews."""
        updated = queryset.update(is_active=False)
        self.message_user(request, _("Successfully deactivated %(count)d reviews.") % {'count': updated})
    deactivate_reviews.short_description = _("Deactivate selected reviews")

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:review_id>/activate/',
                self.admin_site.admin_view(self.activate_review),
                name='reviews_review_activate',
            ),
            path(
                '<int:review_id>/deactivate/',
                self.admin_site.admin_view(self.deactivate_review),
                name='reviews_review_deactivate',
            ),
        ]
        return custom_urls + urls

    def activate_review(self, request, review_id, *args, **kwargs):
        """View to activate a single review."""
        from django.shortcuts import redirect
        from django.contrib import messages
        
        try:
            review = Review.objects.get(id=review_id)
            review.is_active = True
            review.save()
            messages.success(request, _("Review has been activated."))
        except Review.DoesNotExist:
            messages.error(request, _("Review not found."))
        
        return redirect('admin:reviews_review_changelist')

    def deactivate_review(self, request, review_id, *args, **kwargs):
        """View to deactivate a single review."""
        from django.shortcuts import redirect
        from django.contrib import messages
        
        try:
            review = Review.objects.get(id=review_id)
            review.is_active = False
            review.save()
            messages.success(request, _("Review has been deactivated."))
        except Review.DoesNotExist:
            messages.error(request, _("Review not found."))
        
        return redirect('admin:reviews_review_changelist')

    class Media:
        css = {
            'all': ('css/admin/reviews.css',)
        }
        js = ('js/admin/reviews.js',)


class ReviewStatsAdmin(admin.ModelAdmin):
    change_list_template = 'admin/reviews/review_stats.html'
    date_hierarchy = 'date_created'

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(
            request,
            extra_context=extra_context or {},
        )
        
        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response
            
        # Add statistics to the context
        stats = qs.aggregate(
            total=Count('id'),
            avg_rating=Avg('rating'),
            active=Count('id', filter=Q(is_active=True)),
            inactive=Count('id', filter=Q(is_active=False)),
            rating_5=Count('id', filter=Q(rating=5)),
            rating_4=Count('id', filter=Q(rating=4)),
            rating_3=Count('id', filter=Q(rating=3)),
            rating_2=Count('id', filter=Q(rating=2)),
            rating_1=Count('id', filter=Q(rating=1)),
        )
        
        response.context_data.update({
            'stats': stats,
            'title': _('Review Statistics'),
        })
        
        return response

admin.site.register(Review, ReviewAdmin)
admin.site.register(Review, ReviewStatsAdmin)