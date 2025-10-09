from django.contrib import admin
from django.contrib.sites.models import Site
from django.contrib.auth import get_user_model


Profile = get_user_model()

admin.site.unregister(Site)

class SiteAdmin(admin.ModelAdmin): 
    list_display = ('id', 'domain', 'name') 
    
    
admin.site.register(Site, SiteAdmin)
 
class CustomUserAdmin(admin.ModelAdmin):
    model = Profile
    list_display = ['id',
                    'email',
                    'username',
                    'avatar',
                    'first_name',
                    'last_name',
                    'country',
                    'gender',
                    'is_superuser',
                    'is_active',
                    'is_staff',
                    'date_joined',
                    'last_login',
                    ]
    list_filter = ()
    search_fields = ['email', 'username']
    
    
admin.site.register(Profile, CustomUserAdmin)