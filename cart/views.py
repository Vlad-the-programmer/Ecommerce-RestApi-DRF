from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from .enums import CART_STATUSES
from .models import Cart, CartItem, Coupon, SavedCart, SavedCartItem
from .serializers import (
    CartSerializer, CartItemSerializer, 
    CouponSerializer, SavedCartSerializer,
    SavedCartItemSerializer, ApplyCouponSerializer
)
from common.permissions import IsOwnerOrReadOnly, IsAdminOrReadOnly


class CartViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing shopping carts.
    """
    queryset = Cart.objects.active().select_related('user', 'coupon').prefetch_related('cart_items')
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        """Return only the current user's carts."""
        if self.request.user.is_staff:
            return self.queryset
        return self.queryset.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """Set the user to the current user on creation."""
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'], url_path='apply-coupon')
    def apply_coupon(self, request, pk=None):
        """Apply a coupon to the cart."""
        cart = self.get_object()
        serializer = ApplyCouponSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            coupon = Coupon.objects.get(
                coupon_code=serializer.validated_data['coupon_code'],
                is_deleted=False,
                is_expired=False,
                expiration_date__gt=timezone.now()
            )
            
            # Validate coupon against cart
            if not coupon.is_valid(cart.total_price):
                return Response(
                    {"error": "Coupon is not valid for this cart."},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            cart.coupon = coupon
            cart.save()
            return Response(CartSerializer(cart).data)
            
        except Coupon.DoesNotExist:
            return Response(
                {"error": "Invalid or expired coupon code."},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def checkout(self, request, pk=None):
        """Checkout the cart and create an order."""
        cart = self.get_object()
        
        if cart.cart_items.count() == 0:
            return Response(
                {"error": "Cannot checkout an empty cart."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Here you would typically integrate with a payment processor
        # and create an order. For now, we'll just mark the cart as paid.
        cart.status = CART_STATUSES.PAID
        cart.save()
        
        return Response(
            {"message": "Checkout successful. Order created."},
            status=status.HTTP_200_OK
        )


class CartItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing cart items.
    """
    serializer_class = CartItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        """Return only items in the current user's cart."""
        return CartItem.objects.filter(
            cart__user=self.request.user,
            cart__status=CART_STATUSES.ACTIVE,
            is_deleted=False
        ).select_related('product', 'cart')

    def _get_cart_item_and_cart(self, validated_data):
        cart, _ = Cart.objects.get_or_create(
            user=self.request.user,
            status=CART_STATUSES.ACTIVE,
            defaults={'user': self.request.user}
        )

        # Check if item already exists in cart
        product = validated_data['product']

        return cart.cart_items.filter(
            product=product,
            cart=cart,
            is_deleted=False
        ).first(), cart

    def perform_create(self, serializer):
        """Set the cart to the user's active cart or create a new one."""
        quantity = serializer.validated_data.get('quantity', 1)

        cart_item, cart = self._get_cart_item_and_cart(serializer.validated_data)

        if cart_item:
            # Update quantity if item exists
            cart_item.quantity += quantity
            cart_item.save()
        else:
            # Create new cart item
            serializer.save(cart=cart)

    def perform_destroy(self, instance):
        serializer = self.get_serializer(instance)
        serializer.is_valid(raise_exception=True)

        quantity = serializer.validated_data.get('quantity', 1)
        cart_item, cart = self._get_cart_item_and_cart(serializer.validated_data)

        if cart_item:
            # Update quantity if item exists
            cart_item.quantity -= quantity
            cart_item.save()
        else:
            instance.delete()


class CouponViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing coupons.
    """
    queryset = Coupon.objects.filter(is_deleted=False, is_expired=False)
    serializer_class = CouponSerializer
    permission_classes = [permissions.IsAdminUser, permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter coupons based on user permissions."""
        queryset = self.queryset.filter(expiration_date__gt=timezone.now())
        
        if not self.request.user.is_staff:
            # Non-admin users can only see active, non-expired coupons
            return queryset
            
        return Coupon.all_objects.all()


class SavedCartViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing saved carts.
    """
    serializer_class = SavedCartSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        """Return only the current user's saved carts."""
        return SavedCart.objects.filter(
            user=self.request.user,
            is_deleted=False
        ).prefetch_related('items')
    
    def perform_create(self, serializer):
        """Set the user to the current user on creation."""
        # If this is set as default, unset any other default carts
        if serializer.validated_data.get('is_default', False):
            SavedCart.objects.filter(
                user=self.request.user,
                is_default=True
            ).update(is_default=False)
            
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Restore a saved cart to an active cart."""
        saved_cart = self.get_object()
        
        # Get or create active cart
        cart, _ = Cart.objects.get_or_create(
            user=request.user,
            status='active',
            defaults={'user': request.user}
        )
        
        # Clear existing items in cart
        cart.cart_items.all().delete()
        
        # Add items from saved cart to active cart
        for item in saved_cart.items.all():
            CartItem.objects.create(
                cart=cart,
                product=item.product,
                quantity=item.quantity,
                price=item.price
            )
        
        return Response({
            'message': 'Cart restored successfully',
            'cart': CartSerializer(cart).data
        }, status=status.HTTP_200_OK)


class SavedCartItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing saved cart items.
    """
    serializer_class = SavedCartItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        """Return only items in the current user's saved carts."""
        return SavedCartItem.objects.filter(
            saved_cart__user=self.request.user,
            is_deleted=False
        ).select_related('product', 'saved_cart')
    
    def perform_create(self, serializer):
        """Ensure the saved cart belongs to the current user."""
        saved_cart = serializer.validated_data['saved_cart']
        if saved_cart.user != self.request.user:
            raise permissions.exceptions.PermissionDenied("You do not have permission to add items to this cart.")
        
        # Set price from product if not provided
        if 'price' not in serializer.validated_data:
            serializer.validated_data['price'] = serializer.validated_data['product'].price
            
        serializer.save()

