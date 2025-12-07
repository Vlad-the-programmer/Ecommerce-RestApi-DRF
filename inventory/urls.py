from django.urls import path, include
from rest_framework.routers import DefaultRouter

from inventory.views import (
    WarehouseViewSet,
    InventoryViewSet,
    InventoryByProductViewSet,
    InventoryByWarehouseViewSet
)

router = DefaultRouter()
router.register(r'warehouses', WarehouseViewSet, basename='warehouse')
router.register(r'inventory', InventoryViewSet, basename='inventory')
router.register(r'inventory-by-product', InventoryByProductViewSet, basename='inventory-by-product')
router.register(r'inventory-by-warehouse', InventoryByWarehouseViewSet, basename='inventory-by-warehouse')

warehouse_detail = WarehouseViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy'
})

warehouse_inventory = WarehouseViewSet.as_view({
    'get': 'inventory'
})

warehouse_low_stock = WarehouseViewSet.as_view({
    'get': 'low_stock'
})

inventory_summary = InventoryViewSet.as_view({
    'get': 'summary'
})

inventory_adjust_stock = InventoryViewSet.as_view({
    'post': 'adjust_stock'
})

urlpatterns = [
    path('', include(router.urls)),
    
    path('warehouses/<int:pk>/inventory/', warehouse_inventory, name='warehouse-inventory'),
    path('warehouses/<int:pk>/low-stock/', warehouse_low_stock, name='warehouse-low-stock'),
    
    path('inventory/summary/', inventory_summary, name='inventory-summary'),
    path('inventory/<int:pk>/adjust-stock/', inventory_adjust_stock, name='inventory-adjust-stock'),
]
