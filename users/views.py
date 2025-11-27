import logging

from drf_spectacular.utils import extend_schema, OpenApiResponse

from django.db.models import Q
from django.contrib.auth import logout
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.auth import get_user_model

from rest_framework.generics import CreateAPIView

from rest_framework import viewsets, parsers, serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status
from rest_framework.permissions import AllowAny

from .permissions import IsProfileOwnerOrAdmin, IsProfileOwner
from .serializers import (
    ProfileDetailsUpdateSerializer,
    EmailChangeRequestSerializer,
    EmailChangeConfirmSerializer
)

from .models import Profile


logger = logging.getLogger(__name__)
User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    User management viewset.
    Handles: list/search, retrieve/update/delete (excludes create).
    """
    queryset = Profile.objects.all()
    lookup_field = 'uuid'
    lookup_url_kwarg = 'pk'
    serializer_class = ProfileDetailsUpdateSerializer
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    http_method_names = ['get', 'put', 'patch', 'delete', 'head', 'options']  # Exclude 'post'

    def get_permissions(self):
        """
        Assign permissions based on action.
        """
        if self.action == 'list':
            # Anyone can list users
            return [AllowAny()]
        elif self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            # Only profile owners or admins can access specific profiles
            return [IsAuthenticated(), IsProfileOwnerOrAdmin()]
        elif self.action in ['delete_profile']:
            # Only profile owners can delete their own profile
            return [IsAuthenticated(), IsProfileOwner()]
        else:
            return [IsAuthenticated()]

    def get_queryset(self):
        """
        Get queryset with permission check.
        """
        queryset = Profile.objects.all()

        # If user is not staff, only show their own profile in detail views
        if not self.request.user.is_staff and self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            queryset = queryset.filter(user=self.request.user)

        search_query = self.request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(user__username__icontains=search_query) |
                Q(user__first_name__icontains=search_query) |
                Q(user__last_name__icontains=search_query) |
                Q(user__email__icontains=search_query)
            )
        return queryset.order_by('-user__date_joined').only(
            'uuid', 'user__username', 'user__email', 'user__first_name', 'user__last_name',
            'user__date_joined', 'user__last_login', 'is_active', 'is_deleted', 'user__is_staff',
            'user__is_superuser', 'date_of_birth', 'gender', 'country', 'phone_number',
            'avatar', 'date_updated', 'date_created'
        )

    def get_object(self):
        """
        Get object with permission check.
        """
        obj = super().get_object()

        # Check object-level permissions
        self.check_object_permissions(self.request, obj)

        return obj

    def perform_destroy(self, instance):
        """
        Soft delete both profile and user.
        """
        user = instance.user

        instance.delete()
        user.delete()

        logger.debug(f"Soft deleted profile {instance.uuid} and user {user.email}")

    # Override create method to disable it
    def create(self, request, *args, **kwargs):
        return Response(
            {'detail': _('User registration is handled through the registration endpoint.')},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    @action(detail=True, methods=['delete'], url_path='delete-profile')
    def delete_profile(self, request: Request, pk: str=None):
        profile = self.get_object()
        self.perform_destroy(profile)
        logout(request)
        return Response({'detail': _('User deleted successfully.')}, status=status.HTTP_204_NO_CONTENT)


class EmailChangeRequestView(CreateAPIView):
    """
    Request to change user email address.
    Sends confirmation email to the new address.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EmailChangeRequestSerializer

    @extend_schema(
        request=EmailChangeRequestSerializer,
        responses={
            200: OpenApiResponse(description="Confirmation email sent to new address"),
            400: OpenApiResponse(description="Invalid input"),
        }
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = serializer.save()
            return Response(result, status=status.HTTP_200_OK)
        except serializers.ValidationError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class EmailChangeConfirmView(CreateAPIView):
    """
    Confirm email change using token from confirmation email.
    """
    serializer_class = EmailChangeConfirmSerializer

    @extend_schema(
        request=EmailChangeConfirmSerializer,
        responses={
            200: OpenApiResponse(description="Email changed successfully"),
            400: OpenApiResponse(description="Invalid token or email"),
        }
    )
    def create(self, request, uidb64, email_b64, token, *args, **kwargs):
        data = {
            'uidb64': uidb64,
            'email_b64': email_b64,
            'token': token
        }

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        try:
            result = serializer.save()
            return Response(
                {"detail": result["detail"]},
                status=status.HTTP_200_OK
            )
        except serializers.ValidationError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

