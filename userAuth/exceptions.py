from django.utils.translation import gettext_lazy as _
from typing import Optional, List
# REST FRAMEWORK
from rest_framework.exceptions import APIException, ValidationError


class NotOwner(APIException):
    status_code = 403
    default_detail = _('You cannot access a profile if you are not it\'s owner!!!')
    default_code = 'access_denied'


class UserOrTokenNotValid(APIException):
    status_code = 406
    default_detail = _("User is None or token is not valid!")
    default_code = 'activation_not_successful'


class UserAlreadyExists(APIException):
    status_code = 400  # Changed from 302 to 400 as 302 is for redirects
    default_detail = _("A user with this email already exists.")
    default_code = 'user_exists'


class InvalidPasswordFormat(ValidationError):
    """
    Exception raised when a password doesn't meet the required format.
    """
    def __init__(
        self, 
        message: Optional[str] = None, 
        code: str = 'invalid_password_format',
        params: Optional[dict] = None
    ):
        detail = message or _(
            'Password must be at least 8 characters long and contain at least one '
            'uppercase letter, one lowercase letter, and one number.'
        )
        super().__init__(detail=detail, code=code)
        self.params = params or {}


class WeakPasswordError(ValidationError):
    """
    Exception raised when a password is considered too weak.
    """
    def __init__(
        self, 
        message: Optional[str] = None, 
        code: str = 'password_too_weak',
        help_text: Optional[str] = None,
        params: Optional[dict] = None
    ):
        detail = message or _(
            'This password is too weak. Please choose a stronger password.'
        )
        super().__init__(detail=detail, code=code)
        self.help_text = help_text
        self.params = params or {}
        
    @classmethod
    def from_validation_errors(
        cls, 
        validation_errors: List[str],
        code: str = 'password_validation_failed'
    ) -> 'WeakPasswordError':
        """
        Create a WeakPasswordError from a list of validation error messages.
        """
        help_text = _("Password requirements: ") + ", ".join(validation_errors)
        return cls(
            message=_("Password does not meet requirements."),
            code=code,
            help_text=help_text
        )
