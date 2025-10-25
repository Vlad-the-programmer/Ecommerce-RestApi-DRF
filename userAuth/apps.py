from django.apps import AppConfig


class UserAuthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'userAuth'
    label = 'user_auth'  # Add a custom label to avoid conflicts

    def ready(self):
        import userAuth.signals