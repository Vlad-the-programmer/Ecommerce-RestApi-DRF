import pytest
from django.urls import reverse
from rest_framework import status

from category.models import Category
from category.serializers import (
    CategoryListSerializer,
    CategoryDetailSerializer,
    CategoryTreeSerializer
)


@pytest.fixture
def category_data():
    """Sample category data for testing."""
    return {
        'name': 'Test Category',
        'description': 'Test description',
    }


@pytest.fixture
def subcategory_data():
    """Sample subcategory data for testing."""
    return {
        'name': 'Test Subcategory',
        'description': 'Test subcategory description',
    }


@pytest.fixture
def create_category(db, category_data):
    """Create and return a category instance."""
    return Category.objects.create(**category_data)


@pytest.fixture
def create_subcategory(db, create_category, subcategory_data):
    """Create and return a subcategory instance."""
    parent = create_category
    return Category.objects.create(parent=parent, **subcategory_data)


@pytest.fixture
def create_category_tree(db, category_data, subcategory_data):
    """Create a category tree with multiple levels."""
    # Create root categories
    root1 = Category.objects.create(
        name='Root 1',
        description='Root category 1'
    )
    root2 = Category.objects.create(
        name='Root 2',
        description='Root category 2'
    )
    
    # Create subcategories
    sub1 = Category.objects.create(
        name='Sub 1',
        description='Subcategory 1',
        parent=root1
    )
    sub2 = Category.objects.create(
        name='Sub 2',
        description='Subcategory 2',
        parent=root1
    )
    
    # Create sub-subcategories
    Category.objects.create(
        name='Sub-Sub 1',
        description='Sub-subcategory 1',
        parent=sub1
    )
    
    return {
        'root1': root1,
        'root2': root2,
        'sub1': sub1,
        'sub2': sub2,
    }


@pytest.fixture
def category_list_url():
    """URL for category list endpoint."""
    return reverse('v1:category-list')


@pytest.fixture
def category_detail_url(create_category):
    """URL for category detail endpoint."""
    def _category_detail_url(category=None):
        if category is None:
            category = create_category
        return reverse('v1:category-detail', kwargs={'slug': category.slug})
    return _category_detail_url


@pytest.fixture
def category_children_url(create_category):
    """URL for category children endpoint."""
    def _category_children_url(category=None):
        if category is None:
            category = create_category
        return reverse('v1:category-children', kwargs={'slug': category.slug})
    return _category_children_url


@pytest.fixture
def category_tree_url():
    """URL for category tree endpoint."""
    return reverse('v1:category-tree')


@pytest.fixture
def bulk_create_url():
    """URL for bulk create endpoint."""
    return reverse('v1:category-bulk-create')


@pytest.fixture
def bulk_update_url():
    """URL for bulk update endpoint."""
    return reverse('v1:category-bulk-update')
