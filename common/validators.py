from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


class FileSizeValidator:
    """
    Validator for checking the size of uploaded files.
    """
    message = _('File size must be at most %(max_size)s. Your file is %(size)s.')
    code = 'file_size'

    def __init__(self, max_size, message=None, code=None):
        self.max_size = max_size
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code

    def __call__(self, value):
        if value.size > self.max_size:
            raise ValidationError(
                self.message,
                code=self.code,
                params={
                    'max_size': self._format_size(self.max_size),
                    'size': self._format_size(value.size)
                }
            )

    def _format_size(self, size):
        """Format the size to a human-readable format."""
        for unit in ['bytes', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"