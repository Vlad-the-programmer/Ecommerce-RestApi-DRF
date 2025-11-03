from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save



@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def handle_user_creation(sender, instance, created, *args, **kwargs):
    if created:
        # If email verification is enabled and the user is not a superuser or staff, set is_active to False
        if settings.ACCOUNT_EMAIL_VERIFICATION != 'none' and not instance.is_superuser and not instance.is_staff:
            instance.is_active = False
            instance.save(update_fields=['is_active'])

            # If profile exists, also set it to inactive
            if hasattr(instance, 'profile'):
                instance.profile.is_active = False
                instance.profile.save(update_fields=['is_active'])

