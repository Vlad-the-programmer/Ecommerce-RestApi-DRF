from threading import local

_thread_locals = local()

def get_current_request():
    """Return the current request from thread local storage."""
    return getattr(_thread_locals, 'request', None)

def get_current_user():
    """Return the current user from thread local storage."""
    request = get_current_request()
    if request:
        return getattr(request, 'user', None)
    return None

class ThreadLocalMiddleware:
    """Middleware that provides access to the current request and user in model managers."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.request = request
        try:
            return self.get_response(request)
        finally:
            _thread_locals.request = None