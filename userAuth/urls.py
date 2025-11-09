from django.urls import path, include
from dj_rest_auth.registration.views import ResendEmailVerificationView
from dj_rest_auth.views import PasswordResetConfirmView
from dj_rest_auth.urls import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetView,
)

from .views import CustomRegisterView, VerifyEmailView, CustomUserDetailsView


app_name = 'userAuth'


urlpatterns = [
    # Authentication URLs
    path('login/', LoginView.as_view(), name='rest_login'),

    # URLs that require a user to be logged in with a valid session / token.
    path('logout/', LogoutView.as_view(), name='rest_logout'),

    # Override user details endpoint in dj-rest-auth urls to allow only get requests
    path('user/', CustomUserDetailsView.as_view(), name='rest_user_details'),

    path('password/change/', PasswordChangeView.as_view(), name='rest_password_change'),

    path('password/reset/', PasswordResetView.as_view(), name='rest_password_reset'),
    path('password/reset/confirm/<uidb64>/<token>/',
         PasswordResetConfirmView.as_view(),
         name='password_reset_confirm'),

    # Registration endpoints
    path('registration/', include([
        path('', CustomRegisterView.as_view(), name='rest_register'),
        path('verify-email/', VerifyEmailView.as_view(), name='rest_verify_email'),
        path('resend-email/', ResendEmailVerificationView.as_view(), name='rest_resend_email'),
    ])),
]