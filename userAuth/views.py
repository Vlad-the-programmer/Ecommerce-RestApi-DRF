from django.contrib.auth import get_user_model

from rest_framework import parsers

from dj_rest_auth.registration.views import (
     RegisterView as DjRestAuthRegisterView,
    VerifyEmailView as BaseVerifyEmailView
)
from rest_framework.response import Response
from rest_framework import status
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse

from users.models import Gender

Profile = get_user_model()


class CustomRegisterView(DjRestAuthRegisterView):
    """
    Custom registration view that adds support for file uploads.
    """
    # Add support for file uploads
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

    @extend_schema(
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'email': {
                        'type': 'string',
                        'format': 'email',
                        'description': 'User email address (must be unique)'
                    },
                    'first_name': {
                        'type': 'string',
                        'description': 'User first name',
                        'minLength': 1,
                        'maxLength': 30
                    },
                    'last_name': {
                        'type': 'string',
                        'description': 'User last name',
                        'minLength': 1,
                        'maxLength': 30
                    },
                    'username': {
                        'type': 'string',
                        'description': 'Username (optional, defaults to email username if not provided)',
                        'maxLength': 100,
                        'pattern': '^[a-zA-Z0-9_]+$',
                        'nullable': True
                    },
                    'password': {
                        'type': 'string',
                        'format': 'password',
                        'description': 'Password (min 8 chars, must contain uppercase, lowercase, and number)'
                    },
                    'password2': {
                        'type': 'string',
                        'format': 'password',
                        'description': 'Confirm password (must match password)'
                    },
                    'gender': {
                        'type': 'string',
                        'enum': [gender[0] for gender in Gender.choices],
                        'description': 'User gender',
                        'nullable': True
                    },
                    'country': {
                        'type': 'string',
                        'description': 'ISO 3166-1 alpha-2 country code (e.g., US, GB, DE)',
                        'nullable': True
                    },
                    'featured_image': {
                        'type': 'string',
                        'format': 'binary',
                        'description': 'Profile picture (JPEG, PNG, or GIF, max 5MB)',
                        'nullable': True
                    }
                },
                'required': ['email', 'first_name', 'last_name', 'password', 'password2']
            }
        },
        responses={
            201: OpenApiResponse(
                description='User registered successfully',
                examples=[
                    OpenApiExample(
                        'Success Response',
                        value={
                            'detail': 'User registered successfully',
                            'user_id': 1,
                            'email': 'user@example.com'
                        },
                        status_codes=['201']
                    )
                ]
            ),
            400: OpenApiResponse(
                description='Bad Request',
                examples=[
                    OpenApiExample(
                        'Error Response',
                        value={
                            'username': ['This field is required.'],
                            'email': ['Enter a valid email address.']
                        },
                        status_codes=['400']
                    )
                ]
            )
        }
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_serializer(self, *args, **kwargs):
        # Make sure to pass the request context to the serializer
        serializer_class = self.get_serializer_class()
        kwargs['context'] = self.get_serializer_context()
        if self.request and hasattr(self.request, 'data') and self.request.data:
            # Handle both MultiValueDict and regular dict
            data = self.request.data
            if hasattr(data, 'dict'):
                kwargs['data'] = data.dict()
            else:
                kwargs['data'] = data
        return serializer_class(*args, **kwargs)

class VerifyEmailView(BaseVerifyEmailView):
    """
    Custom email verification view that handles both GET and POST requests.
    """

    def get(self, request, *args, **kwargs):
        # Get parameters from URL first, then fall back to query params or request data
        uid = kwargs.get('uidb64') or request.query_params.get('uid') or request.data.get('uid')
        token = kwargs.get('token') or request.query_params.get('token') or request.data.get('token')

        if not uid or not token:
            return Response(
                {'detail': 'Missing UID or token in the verification link.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Clean and decode the UID
            try:
                # Remove any URL encoding if present
                import urllib.parse
                uid = urllib.parse.unquote(uid)

                # Decode the base64 UID
                uid = force_str(urlsafe_base64_decode(uid))
                user = Profile._default_manager.get(pk=uid)
            except (TypeError, ValueError, OverflowError, Profile.DoesNotExist) as e:
                return Response(
                    {'detail': 'Invalid user ID in verification link.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verify the token
            if not default_token_generator.check_token(user, token):
                return Response(
                    {'detail': 'Invalid or expired verification token.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # If we get here, the token is valid - activate the user
            if not user.is_active:
                user.is_active = True
                user.save()

                # Update EmailAddress if using allauth
                try:
                    from allauth.account.models import EmailAddress
                    email_address = EmailAddress.objects.get_for_user(user, user.email)
                    email_address.verified = True
                    email_address.save()
                except Exception:
                    pass  # Skip if allauth is not used

            return Response(
                {'detail': 'Email successfully verified. You can now log in.'},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Email verification error: {str(e)}', exc_info=True)

            return Response(
                {
                    'detail': 'An error occurred while verifying your email. Please try again or request a new verification email.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



