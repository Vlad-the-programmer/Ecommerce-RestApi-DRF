from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
# REST FRAMEWORK 
from rest_framework.authtoken.models import Token


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user(sender, instance, created, *args, **kwargs):
    if created:
        if not instance.username:
            instance.username = instance.email.split('@')[0]
            
        instance.username.lower()
        instance.save()
        
        Token.objects.get_or_create(user=instance)
        print('Token ', Token.objects.get(user=instance))
        print('user id ', instance.id)
        
        
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def update_profile(sender, instance, created, *args, **kwargs):
    if created == False:
        token = Token.objects.get_or_create(user=instance)
        print('Token', token)
