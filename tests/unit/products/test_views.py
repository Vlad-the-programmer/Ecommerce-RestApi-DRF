import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model

from products.models import Product
from tests.conftest import admin_client

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestProductViewSet:
    def test_list_products_unauthenticated(self, client, product_factory, product_list_url):
        """Test that anyone can list products"""
        response = client.get(product_list_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['product_name'] == product_factory().product_name

    def test_retrieve_product_unauthenticated(self, client, product_factory, product_detail_url):
        """Test that anyone can retrieve a product"""
        response = client.get(product_detail_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['product_name'] == product_factory().product_name

    def test_create_product_requires_authentication(self, admin_client, product_list_url, category_factory):
        """Test that creating a product requires authentication"""
        data = {
            'product_name': 'New Product',
            'category': category_factory().id,
            'price': '199.99',
            'product_description': 'New product description'
        }
        response = admin_client.post(product_list_url, data)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_product_as_admin(self, admin_client, admin_user, product_list_url, category_factory):
        """Test that admin can create a product"""
        
        data = {
            'product_name': 'Admin Product',
            'category_factory': category_factory().id,
            'price': '299.99',
            'product_description': 'Admin created product',
            'status': 'published'
        }
        response = admin_client.post(product_list_url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['product_name'] == 'Admin Product'

    def test_update_product_as_admin(self, admin_client, admin_user, product_detail_url):
        """Test that admin can update a product"""
        
        data = {'product_name': 'Updated Product Name'}
        response = admin_client.patch(product_detail_url, data)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['product_name'] == 'Updated Product Name'

    def test_delete_product_as_admin(self, admin_client, admin_user, product_factory, product_detail_url):
        """Test that admin can delete a product"""
        
        response = admin_user.delete(product_detail_url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Product.objects.filter(pk=product_factory().pk).exists()

    def test_digital_products_endpoint(self, client, digital_product):
        """Test the digital products endpoint"""
        url = reverse('products:product-digital-products')
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['product_name'] == digital_product.product_name

    def test_service_products_endpoint(self, client, service_product):
        """Test the service products endpoint"""
        url = reverse('products:product-service-products')
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['product_name'] == service_product.product_name

    def test_product_variants_endpoint(self, client, product_variant):
        """Test the product variants endpoint"""
        url = reverse('products:product-variants', kwargs={'pk': product_variant.pk})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['sku'] == product_variant.sku


class TestProductVariantViewSet:
    def test_list_variants_requires_auth(self, client, variant_list_url):
        """Test that listing variants requires authentication"""
        response = client.get(variant_list_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_variants_as_admin(self, admin_client, admin_user, product_variant, variant_list_url):
        """Test that admin can list variants"""
        response = admin_client.get(variant_list_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['sku'] == product_variant.sku

    def test_create_variant_as_admin(self, admin_client, admin_user, product_factory, variant_list_url):
        """Test that admin can create a variant"""
        data = {
            'product': product_factory().id,
            'sku': 'NEW-SKU-001',
            'cost_price': '75.00',
            'price_adjustment': '15.00',
            'stock_quantity': 50
        }
        response = admin_client.post(variant_list_url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['sku'] == 'NEW-SKU-001'


class TestProductImageViewSet:
    def test_list_images_requires_auth(self, client, image_list_url):
        """Test that listing images requires authentication"""
        response = client.get(image_list_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_upload_image_as_admin(self, admin_client, admin_user, product_factory, image_list_url):
        """Test that admin can upload an image"""
        data = {
            'product': product_factory().id,
            'alt_text': 'Test Image',
            'is_primary': True
        }
        with open('media/test_image.jpg', 'rb') as img:
            data['image'] = img
            response = admin_client.post(image_list_url, data, format='multipart')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'image' in response.data


class TestLocationViewSet:
    def test_list_locations_requires_auth(self, client, location_list_url):
        """Test that listing locations requires authentication"""
        response = client.get(location_list_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_location_as_admin(self, admin_client, admin_user, location_list_url):
        """Test that admin can create a location"""
        data = {
            'name': 'New Location',
            'street_address': '456 Test Ave',
            'city': 'New Test City',
            'state_province': 'New Test State',
            'postal_code': '54321',
            'country': 'New Test Country'
        }
        response = admin_client.post(location_list_url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == 'New Location'
