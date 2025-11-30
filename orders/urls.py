from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'orders', views.OrderViewSet, basename='order')
router.register(r'order-items', views.OrderItemViewSet, basename='orderitem')
router.register(r'order-taxes', views.OrderTaxViewSet, basename='ordertax')
router.register(r'order-status-history', views.OrderStatusHistoryViewSet, basename='orderstatushistory')
router.register(r'admin/orders', views.AdminOrderViewSet, basename='admin-order')

