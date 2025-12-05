from rest_framework import status
from rest_framework.response import Response


class SoftDeleteMixin:
    def perform_destroy(self, instance):
        """
        Soft delete the instance instead of actually deleting it.
        """
        try:
            instance.delete()
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )