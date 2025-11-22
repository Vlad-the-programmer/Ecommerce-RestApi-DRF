import pytest
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

from cart.enums import CART_STATUSES


class TestCartModel:
    """Test cases for the Cart model."""
    
    def test_create_cart(self, cart_factory):
        """Test creating a new cart."""
        cart = cart_factory()
        assert cart.id is not None
        assert cart.status == CART_STATUSES.ACTIVE
        assert cart.user is not None
        assert cart.coupon is None
        assert str(cart) == f"Cart {cart.id}"

    def test_cart_total_with_items(self, cart_item_factory):
        """Test calculating cart total with items."""
        cart_item1 = cart_item_factory(quantity=2, price=Decimal('10.00'))
        cart_item2 = cart_item_factory(cart=cart_item1.cart, quantity=1, price=Decimal('20.00'))
        
        assert cart_item1.cart.total == Decimal('40.00')

    def test_apply_coupon(self, cart_item_factory, coupon_factory):
        """Test applying a coupon to a cart."""
        cart_item = cart_item_factory(price=Decimal('100.00'), quantity=1)
        coupon = coupon_factory(
            product=cart_item.product,
            discount_amount=15,
            minimum_amount=50
        )
        
        cart = cart_item.cart
        cart.apply_coupon(coupon)
        
        assert cart.coupon == coupon
        assert cart.total == Decimal('85.00')  # 100 - 15%

    def test_clear_cart(self, cart_item_factory):
        """Test clearing all items from cart."""
        cart_item = cart_item_factory()
        cart = cart_item.cart
        
        cart.clear()
        
        assert cart.items.count() == 0
        assert cart.total == Decimal('0.00')


class TestCartItemModel:
    """Test cases for the CartItem model."""
    
    def test_create_cart_item(self, cart_item_factory):
        """Test creating a new cart item."""
        cart_item = cart_item_factory(quantity=2, price=Decimal('15.50'))
        
        assert cart_item.id is not None
        assert cart_item.quantity == 2
        assert cart_item.price == Decimal('15.50')
        assert cart_item.subtotal == Decimal('31.00')  # 15.50 * 2
        assert str(cart_item) == f"{cart_item.product.name} - {cart_item.quantity}"

    def test_update_quantity(self, cart_item_factory):
        """Test updating cart item quantity."""
        cart_item = cart_item_factory(quantity=1, price=Decimal('10.00'))
        
        cart_item.quantity = 3
        cart_item.save()
        
        assert cart_item.quantity == 3
        assert cart_item.subtotal == Decimal('30.00')


class TestCouponModel:
    """Test cases for the Coupon model."""
    
    def test_create_coupon(self, coupon_factory):
        """Test creating a new coupon."""
        coupon = coupon_factory(
            coupon_code="TEST20",
            discount_amount=20,
            minimum_amount=100
        )
        
        assert coupon.id is not None
        assert coupon.is_expired is False
        assert coupon.is_valid() is True
        assert str(coupon) == f"TEST20 (20% off)"

    def test_expired_coupon(self, coupon_factory):
        """Test that expired coupons are marked as invalid."""
        coupon = coupon_factory(
            expiration_date=timezone.now() - timedelta(days=1)
        )
        
        assert coupon.is_expired is True
        assert coupon.is_valid() is False

    def test_minimum_amount_validation(self, coupon_factory, cart_item_factory):
        """Test that coupon is only valid for carts meeting minimum amount."""
        coupon = coupon_factory(minimum_amount=100)
        cart_item = cart_item_factory(price=Decimal('50.00'), quantity=1)
        
        # Cart total is 50, minimum is 100
        assert cart_item.cart.total == Decimal('50.00')
        assert coupon.is_valid_for_cart(cart_item.cart) is False
        
        # Update cart to meet minimum
        cart_item.quantity = 2  # 50 * 2 = 100
        cart_item.save()
        
        assert coupon.is_valid_for_cart(cart_item.cart) is True


class TestSavedCartModel:
    """Test cases for the SavedCart model."""
    
    def test_create_saved_cart(self, saved_cart_factory):
        """Test creating a new saved cart."""
        saved_cart = saved_cart_factory(name="Test Cart")
        
        assert saved_cart.id is not None
        assert saved_cart.name == "Test Cart"
        assert saved_cart.is_default is False
        assert str(saved_cart) == f"{saved_cart.user.username}'s saved cart: Test Cart"

    def test_restore_saved_cart(self, saved_cart_item_factory):
        """Test restoring a saved cart to an active cart."""
        saved_cart_item = saved_cart_item_factory(quantity=2, price=Decimal('25.00'))
        saved_cart = saved_cart_item.saved_cart
        
        cart = saved_cart.restore_to_cart()
        
        assert cart.user == saved_cart.user
        assert cart.items.count() == 1
        assert cart.items.first().product == saved_cart_item.product
        assert cart.items.first().quantity == saved_cart_item.quantity
        assert cart.total == Decimal('50.00')  # 25 * 2

    def test_make_default(self, saved_cart_factory):
        """Test setting a saved cart as default."""
        saved_cart1 = saved_cart_factory(is_default=True)
        saved_cart2 = saved_cart_factory(user=saved_cart1.user, is_default=False)
        
        # Make cart2 default
        saved_cart2.make_default()
        
        saved_cart1.refresh_from_db()
        saved_cart2.refresh_from_db()
        
        assert saved_cart1.is_default is False
        assert saved_cart2.is_default is True