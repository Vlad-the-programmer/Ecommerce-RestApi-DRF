import pytest
from django.urls import reverse
from products.models import Product, ProductVariant, ProductImage, Location
from tests.unit.cart.conftest import product_factory, category_factory


# @pytest.fixture
# def location():
#     return Location.objects.create(
#         name="Test Location",
#         street_address="123 Test St",
#         city="Test City",
#         state_province="Test State",
#         postal_code="12345",
#         country="Test Country"
#     )
#
#
# @pytest.fixture
# def product(category, location):
#     return Product.objects.create(
#         product_name="Test Product",
#         category=category,
#         price=99.99,
#         product_description="Test description",
#         status='published',
#         stock_status='in_stock',
#         location=location
#     )


@pytest.fixture
def product_variant(product_factory):
    return ProductVariant.objects.create(
        product=product_factory(),
        sku="TEST-SKU-001",
        cost_price=50.00,
        price_adjustment=10.00,
        stock_quantity=100
    )


@pytest.fixture
def product_image(product_factory):
    return ProductImage.objects.create(
        product=product_factory(),
        alt_text="Test Image",
        is_primary=True
    )


@pytest.fixture
def digital_product(category_factory):
    return Product.objects.create(
        product_name="Digital Product",
        category=category_factory(),
        price=29.99,
        product_type='DIGITAL',
        status='published'
    )


@pytest.fixture
def service_product(category_factory):
    return Product.objects.create(
        product_name="Service Product",
        category=category_factory(),
        price=199.99,
        product_type='SERVICE',
        status='published'
    )


@pytest.fixture
def product_list_url():
    return reverse('v1:product-list')


@pytest.fixture
def product_detail_url(product_factory):
    return reverse('v1:product-detail', kwargs={'pk': product_factory().pk})


@pytest.fixture
def variant_list_url():
    return reverse('v1:productvariant-list')


@pytest.fixture
def image_list_url():
    return reverse('v1:productimage-list')


@pytest.fixture
def location_list_url():
    return reverse('v1:location-list')
