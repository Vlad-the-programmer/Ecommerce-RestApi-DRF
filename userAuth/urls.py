from django.urls import path, include
from dj_rest_auth.registration.views import ResendEmailVerificationView
from dj_rest_auth.views import PasswordResetConfirmView
from .views import CustomRegisterView, VerifyEmailView

app_name = 'userAuth'

urlpatterns = [
    # Authentication URLs
    path('dj_rest_auth/', include('dj_rest_auth.urls')),

    # Registration and email verification endpoints
    path('dj_rest_auth/registration/', include([
        path('', CustomRegisterView.as_view(), name='register'),
        path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
        path('verify-email/confirm/<str:uidb64>/<str:token>/', VerifyEmailView.as_view(), name='verify-email-confirm'),
        path('resend-email/', ResendEmailVerificationView.as_view(), name='resend-email'),
    ])),

    # Password reset endpoints
    path('password/reset/confirm/<uidb64>/<token>/',
         PasswordResetConfirmView.as_view(),
         name='password_reset_confirm'),
]

