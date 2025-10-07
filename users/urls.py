from django.urls import path
from .views import UserViewSet

app_name = 'users'

urlpatterns = [
    # List users (admin only)
    path('', UserViewSet.as_view({
        'get': 'list',
    }), name='user-list'),
    
    # Retrieve and Update
    path('<uuid:pk>/', UserViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
    }), name='user-detail'),
    
    # Custom delete profile endpoint
    path('<uuid:pk>/delete-profile/',
         UserViewSet.as_view({'delete': 'delete_profile'}), 
         name='user-delete-profile'),

]
