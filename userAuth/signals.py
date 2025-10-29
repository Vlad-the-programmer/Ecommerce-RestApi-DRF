from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
# REST FRAMEWORK 
from rest_framework.authtoken.models import Token



@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user(sender, instance, created, *args, **kwargs):
    if created:
        if settings.ACCOUNT_EMAIL_VERIFICATION != 'none':
            instance.is_active = False
            instance.save()

        Token.objects.get_or_create(user=instance)
        print('Token ', Token.objects.get(user=instance))
        print('user id ', instance.id)

