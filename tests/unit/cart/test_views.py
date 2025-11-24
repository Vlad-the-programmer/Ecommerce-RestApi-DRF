import pytest
from decimal import Decimal
from rest_framework import status

from cart.models import Cart, CartItem, Coupon, SavedCart, SavedCartItem
from cart.enums import CART_STATUSES


@pytest.mark.django_db
class TestCartViewSet:
    """Test cases for the CartViewSet."""
    
    def test_get_cart(self, authenticated_client, cart_factory, cart_list_url, verified_user):
        """Test retrieving the user's cart."""
        user, _, _, _ = verified_user
        cart = cart_factory(user=user)
        
        response = authenticated_client.get(cart_list_url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['id'] == cart.id
    
    def test_apply_coupon(self, authenticated_client, cart_item_factory, coupon_factory, cart_apply_coupon_url, verified_user):
        """Test applying a coupon to the cart."""
        user, _, _, _ = verified_user
        cart_item = cart_item_factory(
            cart__user=user,
            price=Decimal('100.00'),
            quantity=1
        )
        coupon = coupon_factory(
            product=cart_item.product,
            coupon_code="TEST10",
            discount_amount=10,
            minimum_cart_amount=50
        )
        
        response = authenticated_client.post(
            cart_apply_coupon_url(cart_item.cart.id),
            {'coupon_code': 'TEST10'},
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        cart_item.cart.refresh_from_db()
        assert cart_item.cart.coupon == coupon
        assert 'discount_amount' in response.data
        assert Decimal(response.data['total']) == Decimal('90.00')  # 100 - 10%
    
    def test_checkout_cart(self, authenticated_client, cart_item_factory, cart_checkout_url, verified_user):
        """Test checking out a cart."""
        user, _, _, _ = verified_user

        cart_item = cart_item_factory(
            cart__user=user,
            price=Decimal('50.00'),
            quantity=2,
            product__stock_quantity=10
        )
        
        response = authenticated_client.post(cart_checkout_url(cart_item.cart.id))
        
        assert response.status_code == status.HTTP_200_OK
        cart_item.cart.refresh_from_db()
        assert cart_item.cart.status == CART_STATUSES.PAID
        assert 'order_id' in response.data
    
    def test_checkout_insufficient_stock(self, authenticated_client, cart_item_factory, verified_user):
        """Test checkout with insufficient stock."""
        user, _, _, _ = verified_user

        cart_item = cart_item_factory(
            cart__user=user,
            quantity=10,
            product__stock_quantity=5
        )
        
        response = authenticated_client.post(cart_item_factory(cart_item.cart.id))
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'stock' in str(response.data).lower()


@pytest.mark.django_db
class TestCartItemViewSet:
    """Test cases for the CartItemViewSet."""
    
    def test_add_item_to_cart(self, authenticated_client, product_factory, cart_item_list_url):
        """Test adding an item to the cart."""
        product = product_factory(price=Decimal('25.00'))
        
        response = authenticated_client.post(
            cart_item_list_url,
            {
                'product_id': product.id,
                'quantity': 2
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert CartItem.objects.count() == 1
        cart_item = CartItem.objects.first()
        assert cart_item.quantity == 2
        assert cart_item.price == product.price
    
    def test_update_cart_item_quantity(self, authenticated_client, verified_user, cart_item_factory, cart_item_detail_url):
        """Test updating the quantity of a cart item."""
        user, _, _, _ = verified_user

        cart_item = cart_item_factory(
            cart__user=user,
            quantity=1
        )
        
        response = authenticated_client.patch(
            f'{cart_item_detail_url}{cart_item.id}/',
            {'quantity': 3},
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        cart_item.refresh_from_db()
        assert cart_item.quantity == 3
    
    def test_remove_item_from_cart(self, authenticated_client, verified_user, cart_item_factory, cart_item_detail_url):
        """Test removing an item from the cart."""
        user, _, _, _ = verified_user

        cart_item = cart_item_factory(cart__user=user)
        
        response = authenticated_client.delete(f'{cart_item_detail_url,}{cart_item.id}/')
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not CartItem.objects.filter(id=cart_item.id).exists()


@pytest.mark.django_db
class TestCouponViewSet:
    """Test cases for the CouponViewSet."""
    
    def test_create_coupon(self, admin_client, product_factory, coupon_list_url):
        """Test creating a new coupon (admin only)."""
        product = product_factory()
        
        response = admin_client.post(
            coupon_list_url,
            {
                'product': product.id,
                'coupon_code': 'NEWCOUPON',
                'discount_amount': 15,
                'minimum_cart_amount': 100,
                'expiration_date': '2100-12-31T23:59:59Z'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert Coupon.objects.count() == 1
        coupon = Coupon.objects.first()
        assert coupon.coupon_code == 'NEWCOUPON'
        assert coupon.product == product
    
    def test_non_admin_cannot_create_coupon(self, authenticated_client, product_factory, coupon_list_url):
        """Test that non-admin users cannot create coupons."""
        product = product_factory()
        
        response = authenticated_client.post(
            coupon_list_url,
            {
                'product': product.id,
                'coupon_code': 'USERCOUPON',
                'discount_amount': 10,
                'minimum_cart_amount': 50,
                'expiration_date': '2100-12-31T23:59:59Z'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestSavedCartViewSet:
    """Test cases for the SavedCartViewSet."""
    
    def test_save_cart(self, authenticated_client, cart_item_factory, saved_cart_list_url):
        """Test saving the current cart."""
        user, _, _, _ = verified_user

        cart_item = cart_item_factory(cart__user=user)
        
        response = authenticated_client.post(
            saved_cart_list_url,
            {
                'name': 'My Saved Cart',
                'description': 'For later purchase'
            },
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert SavedCart.objects.filter(
            user=verified_user,
            name='My Saved Cart'
        ).exists()
        
        saved_cart = SavedCart.objects.first()
        assert saved_cart.items.count() == 1
    
    def test_restore_saved_cart(self, authenticated_client, saved_cart_item_factory, saved_cart_restore_url):
        """Test restoring a saved cart."""
        user, _, _, _ = verified_user

        saved_cart_item = saved_cart_item_factory(
            saved_cart__user=user
        )
        
        response = authenticated_client.post(saved_cart_restore_url(saved_cart_item.saved_cart.id))
        
        assert response.status_code == status.HTTP_200_OK
        assert Cart.objects.filter(user=verified_user).count() == 2  # Original + restored
        
        # Verify the restored cart has the correct items
        restored_cart = Cart.objects.latest('date_created')
        assert restored_cart.items.count() == 1
        assert restored_cart.items.first().product == saved_cart_item.product
    
    def test_cannot_restore_other_users_cart(self, authenticated_client, user_factory, saved_cart_factory, saved_cart_restore_url):
        """Test that users can only restore their own saved carts."""
        other_user = user_factory()
        saved_cart = saved_cart_factory(user=other_user)
        
        response = authenticated_client.post(saved_cart_restore_url(saved_cart.id))
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
