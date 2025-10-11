from django.contrib import admin
from django.contrib.sites.models import Site
from django.contrib.auth import get_user_model

from users.models import Profile

User = get_user_model()

admin.site.unregister(Site)

class SiteAdmin(admin.ModelAdmin): 
    list_display = ('id', 'domain', 'name') 
    
    
admin.site.register(Site, SiteAdmin)
 
class CustomUserAdmin(admin.ModelAdmin):
    model = Profile
    list_display = ['uuid',
                    'user__email',
                    'user__username',
                    'avatar',
                    'user__first_name',
                    'user__last_name',
                    'country',
                    'gender',
                    'user__is_superuser',
                    'is_active',
                    'user__is_staff',
                    'user__date_joined',
                    'user__last_login',
                    ]
    list_filter = ()
    search_fields = ['email', 'username']
    
    
admin.site.register(Profile, CustomUserAdmin)