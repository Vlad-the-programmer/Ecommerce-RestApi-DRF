from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from django.utils.deconstruct import deconstructible


@deconstructible
class FileSizeValidator:
    """
    Validator for checking the size of uploaded files.
    """
    message = _('File size must be at most %(max_size)s. Your file is %(size)s.')
    code = 'file_size'

    def __init__(self, max_size, message=None, code=None):
        self.max_size = max_size
        self.message = message or _(
            f'File size must be no more than {filesizeformat(max_size)}. '
            f'Your file is %(filesize)s.'
        )
        self.code = code or _('file_too_large')

    def __call__(self, value):
        if value.size > self.max_size:
            raise ValidationError(
                self.message,
                code=self.code,
                params={
                    'max_size': filesizeformat(self.max_size),
                    'filesize': filesizeformat(value.size),
                    'max_size_bytes': self.max_size,
                    'filesize_bytes': value.size,
                }
            )

    def __eq__(self, other):
        return (
                isinstance(other, self.__class__) and
                self.max_size == other.max_size and
                self.message == other.message
        )