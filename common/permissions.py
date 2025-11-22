from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `owner` attribute.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # Instance must have an attribute named 'owner' or 'user'.
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user
            
        # Default deny
        return False


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Global permission to only allow admin users to edit objects.
    Non-admin users can only view objects.
    """
    
    def has_permission(self, request, view):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # Write permissions are only allowed to admin users.
        return request.user and request.user.is_staff


class IsOwner(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to access it.
    More restrictive than IsOwnerOrReadOnly as it doesn't allow read access to non-owners.
    """
    
    def has_object_permission(self, request, view, obj):
        # Instance must have an attribute named 'owner' or 'user'.
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user
            
        # Default deny
        return False


class IsAdminOrOwner(permissions.BasePermission):
    """
    Permission to only allow admin users or the owner of an object to access it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admin users can do anything
        if request.user and request.user.is_staff:
            return True
            
        # Instance must have an attribute named 'owner' or 'user'.
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user
            
        # Default deny
        return False
