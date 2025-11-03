import logging

from rest_framework import permissions
from users.models import Profile


logger = logging.getLogger(__name__)


class IsProfileOwner(permissions.BasePermission):
    """
    Object-level permission to only allow owners of a profile to access or edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Check if the requesting user owns the profile
        if isinstance(obj, Profile):
            return obj.user == request.user
        return False


class IsProfileOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to allow anyone to read, but only owners to edit.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the profile owner
        if isinstance(obj, Profile):
            return obj.user == request.user
        return False


class IsProfileOwnerOrAdmin(permissions.BasePermission):
    """
    Object-level permission to allow owners or admin/staff to access.
    """

    def has_object_permission(self, request, view, obj):
        # Admin users can do anything
        if request.user and (request.user.is_staff or request.user.is_superuser):
            logger.debug(f"Admin access granted for {request.user.email}")
            return True

        # Check if the requesting user owns the profile
        if isinstance(obj, Profile):
            is_owner = obj.user == request.user
            logger.debug(
                f"Owner check: {is_owner} (profile user: {obj.user.email}, request user: {request.user.email})")
            return is_owner

        return False


class IsProfileOwnerOrAdminForWrite(permissions.BasePermission):
    """
    Object-level permission to allow anyone to read, but only owners or admin to write.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Admin users can do anything
        if request.user and request.user.is_staff:
            return True

        # Write permissions are only allowed to the profile owner
        if isinstance(obj, Profile):
            return obj.user == request.user
        return False