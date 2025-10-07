from django.db.models import Q
from django.contrib.auth import logout
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, parsers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status
from rest_framework.permissions import AllowAny

from userAuth.serializers import UserSerializer
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

Profile = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    User management viewset.
    Handles: registration, list/search, retrieve/update/delete.
    """
    queryset = Profile.objects.all()
    serializer_class = UserSerializer
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

    def get_permissions(self):
        if self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        elif self.action in ['list']:
            return [AllowAny()]
        elif self.action in ['change_password']:
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = Profile.objects.prefetch_related('groups', 'user_permissions')
        search_query = self.request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query)
            )
        return queryset.order_by('-date_joined').only(
            'id', 'username', 'email', 'first_name', 'last_name',
            'date_joined', 'last_login', 'is_active', 'is_staff'
        )

    @action(detail=True, methods=['delete'], url_path='delete-profile', permission_classes=[IsAuthenticated])
    def delete_profile(self, request: Request, pk=None):
        profile = get_object_or_404(Profile, pk=pk)
        self.perform_destroy(profile)
        logout(request)
        return Response({'detail': _('Profile deleted successfully.')}, status=status.HTTP_204_NO_CONTENT)




