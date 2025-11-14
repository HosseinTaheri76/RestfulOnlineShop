from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

app_name = 'accounts'

urlpatterns = [
    path(
        'create/',
        views.UserCreateView.as_view(),
        name='create'
    ),
    path(
        'password-login/',
        views.PasswordLoginView.as_view(),
        name='password-login'
    ),
    path(
        'request-otp-login/<str:channel>/',
        views.OTPLoginRequestView.as_view(),
        name='request-otp-login'
    ),
    path(
        'confirm-otp-login/',
        views.OTPLoginConfirmView.as_view(),
        name='confirm-otp-login'
    ),
    path(
        'refresh-token/',
        TokenRefreshView.as_view(),
        name='refresh-token'
    ),
    path(
        'request-email-verification/',
        views.EmailVerificationRequestView.as_view(),
        name='request-email-verification'
    ),
    path(
        'request-phone-verification/',
        views.PhoneVerificationRequestView.as_view(),
        name='request-phone-verification'
    ),
    path(
        'confirm-email-verification/',
        views.EmailVerificationConfirmView.as_view(),
        name='confirm-email-verification'
    ),
    path(
        'confirm-phone-verification/',
        views.PhoneVerificationConfirmView.as_view(),
        name='confirm-phone-verification'
    ),
    path(
        'request-email-change/',
        views.RequestEmailChangeView.as_view(),
        name='request-email-change'
    ),
    path(
        'request-phone-change/',
        views.RequestPhoneChangeView.as_view(),
        name='request-phone-change'
    ),
    path(
        'confirm-email-change/',
        views.ConfirmEmailChangeView.as_view(),
        name='confirm-email-change'
    ),
    path(
        'confirm-phone-change/',
        views.ConfirmPhoneChangeView.as_view(),
        name='confirm-phone-change'
    )
]
