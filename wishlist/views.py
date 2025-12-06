from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, ValidationError

from django.utils.translation import gettext_lazy as _

from common.mixins import SoftDeleteMixin
from common.permissions import IsOwnerOrStaff
from wishlist.models import Wishlist, WishListItem
from wishlist.serializers import (
    WishlistSerializer,
    WishlistItemSerializer,
    WishlistItemCreateSerializer,
    WishlistItemUpdateSerializer,
    WishlistItemMoveToCartSerializer
)
from cart.models import Cart


class WishlistViewSet(SoftDeleteMixin, ModelViewSet):
    """
    API endpoint that allows wishlists to be viewed or edited.
    """
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]

    def get_queryset(self):
        """Return only the current user's wishlists."""
        return Wishlist.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Set the user to the current user on creation."""
        if Wishlist.objects.filter(user=self.request.user).exists():
            raise ValidationError({"detail": _("You already have a wishlist. Use the existing one or update it.")})
        
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def mine(self, request):
        """
        Retrieve the current user's wishlist.
        If no wishlist exists, one will be created.
        """
        wishlist, created = Wishlist.objects.get_or_create_for_user(
            user=request.user,
            name=_("My Wishlist"),
            is_public=False
        )
        serializer = self.get_serializer(wishlist)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def set_public(self, request, pk=None):
        """Set wishlist visibility to public."""
        wishlist = self.get_object()
        wishlist.is_public = True
        wishlist.save(update_fields=['is_public', 'date_updated'])
        return Response({"status": _("Wishlist is now public")})
    
    @action(detail=True, methods=['post'])
    def set_private(self, request, pk=None):
        """Set wishlist visibility to private."""
        wishlist = self.get_object()
        wishlist.is_public = False
        wishlist.save(update_fields=['is_public', 'date_updated'])
        return Response({"status": _("Wishlist is now private")})

    @action(detail=False, methods=['post'])
    def move_all_to_cart(self, request):
        """Move items from wishlist to cart."""
        cart = Cart.objects.get_or_create(
            user=request.user,
            defaults={
                'user': request.user,
                'is_active': True
            }
        )
        wishlist = self.get_object()
        wishlist.move_to_cart(cart)

        return Response({
            'status': 'success',
            'message': _(f"Successfully moved {cart.get_cart_total_quantity()} items to cart")
        })


class WishlistItemViewSet(SoftDeleteMixin, ModelViewSet):
    """
    API endpoint that allows wishlist items to be viewed or edited.
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]
    
    def get_queryset(self):
        """Return only the current user's wishlist items."""
        return WishListItem.objects.filter(
            wishlist__user=self.request.user,
        ).select_related('product', 'variant')
    
    def get_serializer_class(self):
        """Return appropriate serializer class based on action."""
        if self.action == 'create':
            return WishlistItemCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return WishlistItemUpdateSerializer
        return WishlistItemSerializer
    
    def get_wishlist(self):
        """Get or create a wishlist for the current user."""
        wishlist, _ = Wishlist.objects.get_or_create_for_user(
            user=self.request.user,
            name=_("My Wishlist"),
            is_public=False
        )
        return wishlist
    
    def perform_create(self, serializer):
        """Create a new wishlist item."""
        wishlist = self.get_wishlist()
        
        existing_item = wishlist.wishlist_items.filter(
            product_id=serializer.validated_data['product_id'],
            variant_id=serializer.validated_data.get('variant_id'),
        ).first()
        
        if existing_item:
            existing_item.quantity += serializer.validated_data.get('quantity', 1)
            existing_item.save()
            self.instance = existing_item
        else:
            serializer.save(
                wishlist=wishlist,
                user=self.request.user
            )
    
    @action(detail=False, methods=['post'])
    def move_to_cart(self, request):
        """Move items from wishlist to cart."""
        serializer = WishlistItemMoveToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = Cart.objects.get_or_create(
            user=request.user,
            defaults={
                'user': request.user,
                'is_active': True
            }
        )
        wishlist = self.get_wishlist()

        item_ids = serializer.validated_data['item_ids']
        items = self.get_queryset().filter(id__in=item_ids)
        
        if not items.exists():
            raise NotFound(_("No valid wishlist items found"))

        wishlist.move_to_cart(cart, items)

        return Response({
            'status': 'success',
            'message': _(f"Successfully moved {items.count()} items to cart")
        })
    
    @action(detail=True, methods=['post'])
    def update_priority(self, request, pk=None):
        """Update the priority of a wishlist item."""
        item = self.get_object()
        priority = request.data.get('priority')
        
        if not priority or not any(priority == choice[0] for choice in WishListItem.PRIORITY_CHOICES):
            raise ValidationError({"priority": _("Invalid priority value")})
        
        item.priority = priority
        item.save(update_fields=['priority', 'date_updated'])
        
        return Response({
            'status': 'success',
            'item_id': item.id,
            'priority': item.get_priority_display(),
            'message': _("Priority updated successfully")
        })
