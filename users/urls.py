from django.urls import path
from .views import UserViewSet, EmailChangeRequestView, EmailChangeConfirmView


app_name = 'users'


urlpatterns = [
    # List users (admin only)
    path('', UserViewSet.as_view({
        'get': 'list',
    }), name='user-list'),
    
    path('<uuid:pk>/', UserViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
    }), name='user-detail'),
    
    path('<uuid:pk>/delete-profile/',
         UserViewSet.as_view({'delete': 'delete_profile'}), 
         name='user-delete-profile'),

    path('email/change/', EmailChangeRequestView.as_view(), name='email_change_request'),
    path('email/change/confirm/<uidb64>/<email_b64>/<token>/',
         EmailChangeConfirmView.as_view(),
         name='email_change_confirm'),
]
