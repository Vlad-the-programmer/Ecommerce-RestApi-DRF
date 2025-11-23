from rest_framework.routers import DefaultRouter

from . import views


app_name = 'category'

router = DefaultRouter()
router.register(r'categories', views.CategoryViewSet, basename='category')
