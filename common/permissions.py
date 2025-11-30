from rest_framework import permissions
from django.utils.translation import gettext_lazy as _



class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `owner` attribute.
    """
    
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        elif hasattr(obj, 'user'):
            return obj.user == request.user
            
        return False


class IsOwner(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to access it.
    More restrictive than IsOwnerOrReadOnly as it doesn't allow read access to non-owners.
    """
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'user'):
            return obj.user == request.user
            
        return False


class IsAdminOrOwner(permissions.BasePermission):
    """
    Permission to only allow admin users or the owner of an object to access it.
    """
    
    def has_object_permission(self, request, view, obj):
        if request.user and request.user.is_staff:
            return True

        elif hasattr(obj, 'user'):
            return obj.user == request.user
            
        return False


class IsOwnerOrStaff(permissions.BasePermission):
    """
    Permission to only allow owners of an object or staff to access it.
    """
    message = _('You do not have permission to access this resource.')
    
    def has_permission(self, request, view):
        # Allow all authenticated users for list/create actions
        if request.user.is_authenticated:
            return True
        return False
    
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True

        elif hasattr(obj, 'user'):
            return obj.user == request.user
            
        return False


class IsStaffOrReadOnly(permissions.BasePermission):
    """
    The request is authenticated as a staff user, or is a read-only request.
    """
    message = _('You do not have permission to perform this action.')
    
    def has_permission(self, request, view):
        return bool(
            request.method in permissions.SAFE_METHODS or
            (request.user and request.user.is_staff)
        )
