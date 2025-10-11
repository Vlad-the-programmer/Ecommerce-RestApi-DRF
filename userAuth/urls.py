from django.urls import path, include
from dj_rest_auth.registration.views import ResendEmailVerificationView
from dj_rest_auth.views import PasswordResetConfirmView


from .views import CustomRegisterView, VerifyEmailView

app_name = 'userAuth'

urlpatterns = [
    # Authentication URLs
    path('/', include('dj_rest_auth.urls')),

    # Registration endpoints
    path('registration/', include([
        path('', CustomRegisterView.as_view(), name='rest_register'),
        path('verify-email/', VerifyEmailView.as_view(), name='rest_verify_email'),
        path('resend-email/', ResendEmailVerificationView.as_view(), name='rest_resend_email'),
    ])),

    # Password reset confirm (required by dj_rest_auth)
    path('auth/password/reset/confirm/<uidb64>/<token>/',
         PasswordResetConfirmView.as_view(),
         name='password_reset_confirm'),
]

