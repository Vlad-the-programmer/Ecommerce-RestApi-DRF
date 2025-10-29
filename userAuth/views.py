import logging

from django.contrib.auth import get_user_model

from rest_framework import parsers

from dj_rest_auth.registration.views import (
     RegisterView as DjRestAuthRegisterView,
    VerifyEmailView as BaseVerifyEmailView
)
from allauth.account.models import EmailConfirmation
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse

from users.models import Gender


logger = logging.getLogger(__name__)
User = get_user_model()



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
                    'phone_number': {
                        'type': 'string',
                        'description': 'User phone number',
                        'nullable': True
                    },
                    'date_of_birth': {
                        'type': 'string',
                        'format': 'date',
                        'description': 'User date of birth',
                        'nullable': True
                    },
                    'country': {
                        'type': 'string',
                        'description': 'ISO 3166-1 alpha-2 country code (e.g., US, GB, DE)',
                        'nullable': True
                    },
                    'avatar': {
                        'type': 'string',
                        'format': 'binary',
                        'description': 'User picture (JPEG, PNG, or GIF, max 5MB)',
                        'nullable': True
                    }
                },
                'required': ['email', 'first_name', 'last_name', 'phone_number',
                             'date_of_birth', 'password', 'password2']
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
                            'username': 'user',
                            'first_name': 'user',
                            'last_name': 'user',
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
        serializer_class = self.get_serializer_class()
        kwargs['context'] = self.get_serializer_context()
        return serializer_class(*args, **kwargs)


class VerifyEmailView(BaseVerifyEmailView):
    """
    Custom email verification view that handles both GET and POST requests.
    """

    def post(self, request, *args, **kwargs):
        try:
            # Get the confirmation key from request
            key = request.data.get('key', '').strip()  # Strip whitespace
            logger.debug(f"VerifyEmailView - Received key: '{key}'")
            logger.debug(f"VerifyEmailView - Request data: {request.data}")

            if not key:
                logger.warning("VerifyEmailView - Empty or missing key provided")
                return Response(
                    {'detail': 'Verification key is required and cannot be empty.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verify the email
            confirmation = EmailConfirmation.objects.get(key=key)
            logger.debug(f"VerifyEmailView - Found confirmation for: {confirmation.email_address.email}")

            # Confirm the email address
            confirmation.confirm(request)

            # Activate the user and profile
            user = confirmation.email_address.user
            user.is_active = True
            user.save()

            # Activate profile if it exists
            if hasattr(user, 'profile'):
                user.profile.is_active = True
                user.profile.save()
                logger.debug(f"VerifyEmailView - Activated profile for user: {user.email}")

            logger.info(f"VerifyEmailView - Successfully activated user: {user.email}")
            return Response(
                {'detail': 'Email successfully verified. You can now log in.'},
                status=status.HTTP_200_OK
            )

        except EmailConfirmation.DoesNotExist:
            logger.warning(f"VerifyEmailView - Confirmation not found for key: {key}")
            return Response(
                {'detail': 'Invalid verification key.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f'Email verification error: {str(e)}', exc_info=True)
            return Response(
                {
                    'detail': 'An error occurred while verifying your email. '
                              'Please try again or request a new verification email.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )