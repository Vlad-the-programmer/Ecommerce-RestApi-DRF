import uuid
from django.db import models
from django.core import validators
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser, Permission
from django_countries.fields import CountryField
from .managers import UserManager

class Gender(models.TextChoices):
    MALE = "male", _("Male")
    FEMALE = "female", _("Female")
    OTHER = "other", _("Other")


class Profile(AbstractUser):
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    objects = UserManager()
    
    id = models.UUIDField(default=uuid.uuid4, 
                          unique=True,
                          primary_key=True, 
                          editable=False
                        )
    email = models.EmailField(unique=True, 
                              blank=True,
                              null=True, 
                              validators=[
                                            validators.EmailValidator()
                                        ])
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    gender = models.CharField(_('Gender'),
                              max_length=10,
                              choices=Gender,
                              default=_('Male'),
                              null=True)
    country = CountryField(blank_label=_('(select country)'), default='')
    featured_img = models.ImageField(verbose_name=_('A profile image'),
                                     upload_to='profiles', 
                                     default='profiles/profile_default.jpg')
    password = models.CharField(max_length=100, blank=True, null=True)
    username = models.CharField(unique=True, max_length=100, blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True, null=True)
    last_login = models.DateTimeField(_('Last logged in'), auto_now=True,
                                      null=True, blank=True)
    is_staff = models.BooleanField(default=False, blank=True, null=True)
    is_active = models.BooleanField(default=False, blank=True, null=True)
    is_superuser = models.BooleanField(default=False, blank=True, null=True)
    
    def __str__(self):
        return self.email
    
    def has_perm(self, perm, obj=None):
        return self.is_superuser
    
    def has_add_permission(request):
        if request.user.is_staff:
            return True
        return False

    def has_change_permission(request):
        if request.user.is_staff:
            return True
        return False
    
    def has_delete_permission(request):
        if request.user.is_staff:
            return True
        return False
    
    def has_module_perms(self, app_label):
        return True
    
    
    @classmethod
    def get_user_by_email(cls, email):
        try:
            user = cls.objects.get(email__exact=email)
        except:
            user = None
        if user is not None:
            return True
        return False 
    
    @property
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def get_short_name(self):
        return self.username
    
    @property
    def imageURL(self):
        try:
            url = self.featured_img.url
        except:
            url = ''
        return url

    class Meta:
       verbose_name_plural = 'Users'
       ordering = ['email']