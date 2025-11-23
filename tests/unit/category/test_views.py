import pytest
from django.urls import reverse
from rest_framework import status

from category.models import Category
from category.serializers import (
    CategoryListSerializer,
    CategoryDetailSerializer,
    CategoryTreeSerializer
)


class TestCategoryListViewSet:
    """Tests for the CategoryViewSet list and create actions."""
    
    def test_list_categories(self, client, create_category, category_list_url):
        """Test listing categories."""
        response = client.get(category_list_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        
    def test_list_root_categories(self, client, create_category_tree, category_list_url):
        """Test listing only root categories."""
        response = client.get(f"{category_list_url}?parent=root")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2  # Should only return root categories
        
    def test_create_category(self, client, admin_client, category_data, category_list_url):
        """Test creating a new category."""
        response = admin_client.post(category_list_url, category_data)
        assert response.status_code == status.HTTP_201_CREATED
        assert Category.objects.filter(name=category_data['name']).exists()
        
    def test_create_category_unauthenticated(self, client, category_data, category_list_url):
        """Test creating a category without authentication."""
        response = client.post(category_list_url, category_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestCategoryDetailViewSet:
    """Tests for the CategoryViewSet retrieve, update, and delete actions."""
    
    def test_retrieve_category(self, client, create_category, category_detail_url):
        """Test retrieving a category."""
        category = create_category
        url = category_detail_url(category)
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == category.name
        
    def test_update_category(self, admin_client, create_category, category_detail_url):
        """Test updating a category."""
        category = create_category
        url = category_detail_url(category)
        data = {'name': 'Updated Name', 'description': 'Updated description'}
        response = admin_client.patch(url, data)
        assert response.status_code == status.HTTP_200_OK
        category.refresh_from_db()
        assert category.name == 'Updated Name'
        
    def test_delete_category(self, admin_client, create_category, category_detail_url):
        """Test deleting a category."""
        category = create_category
        url = category_detail_url(category)
        response = admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Category.objects.filter(pk=category.pk).exists()


class TestCategoryTreeView:
    """Tests for the category tree view."""
    def test_get_category_tree(self, client, create_category_tree, category_tree_url):
        """Test getting the category tree."""
        response = client.get(category_tree_url)
        assert response.status_code == status.HTTP_200_OK
        # Should return all root categories with their children
        assert len(response.data) == 2
        # First root should have 2 children
        assert len(response.data[0]['children']) == 2
        # First child of first root should have 1 child
        assert len(response.data[0]['children'][0]['children']) == 1


class TestCategoryChildrenView:
    """Tests for the category children view."""
    def test_get_category_children(self, client, create_category_tree, category_children_url):
        """Test getting children of a category."""
        # Get a category with children
        root = Category.objects.get(name='Root 1')
        url = category_children_url(root)
        response = client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Should return 2 children
        assert len(response.data['results']) == 2
        
    def test_get_category_children_empty(self, client, create_category, category_children_url):
        """Test getting children of a category with no children."""
        category = create_category
        url = category_children_url(category)
        response = client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 0


class TestBulkOperations:
    """Tests for bulk create and update operations."""
    
    def test_bulk_create(self, admin_client, bulk_create_url):
        """Test bulk creating categories."""
        data = {
            'categories': [
                {'name': 'Bulk 1', 'description': 'Bulk category 1'},
                {'name': 'Bulk 2', 'description': 'Bulk category 2', 'parent': None}
            ]
        }
        response = admin_client.post(
            bulk_create_url,
            data,
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 2
        assert Category.objects.filter(name__startswith='Bulk').count() == 2
        
    def test_bulk_update(self, admin_client, create_category, bulk_update_url):
        """Test bulk updating categories."""
        category1 = create_category
        category2 = Category.objects.create(name='Category 2', description='Test 2')
        
        data = {
            'ids': [category1.id, category2.id],
            'is_active': False
        }
        
        response = admin_client.patch(
            bulk_update_url,
            data,
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['updated_count'] == 2
        assert not Category.objects.get(pk=category1.id).is_active
        assert not Category.objects.get(pk=category2.id).is_active
