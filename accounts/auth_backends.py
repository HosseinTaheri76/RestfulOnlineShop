from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.utils.translation import gettext

from rest_framework.exceptions import AuthenticationFailed

from otp.models import EmailOTP, PhoneNumberOTP


class PasswordBackend(ModelBackend):

    def check_credentials(self, user, password):
        if user and user.check_password(password):
            if self.user_can_authenticate(user):
                return user
            raise AuthenticationFailed(gettext('This account is inactive.'))
        raise AuthenticationFailed(gettext('Invalid credentials.'))


class OTPBackend(ModelBackend):
    purpose = 'login'
    otp_model = None

    def authenticate(self, request, request_id=None, token=None, **kwargs):

        if not (token and request_id):
            return None

        try:
            otp = self.otp_model.objects.get(request_id=request_id)
            success, details = otp.verify(purpose=self.purpose, raw_token=token)
            if success:
                user = otp.user
                if self.user_can_authenticate(user):
                    return user
                raise AuthenticationFailed(gettext('This account is inactive.'))
            raise AuthenticationFailed(details['reason'])
        except self.otp_model.DoesNotExist:
            return None


class EmailOTPBackend(OTPBackend):
    otp_model = EmailOTP


class PhoneNumberOTPBackend(OTPBackend):
    otp_model = PhoneNumberOTP


class EmailPasswordBackend(PasswordBackend):

    def authenticate(self, request, email=None, password=None, **kwargs):
        if not (email and password):
            return None

        user = get_user_model().objects.filter(email__iexact=email).first()
        return self.check_credentials(user, password)


class PhonePasswordBackend(PasswordBackend):

    def authenticate(self, request, phone_number=None, password=None, **kwargs):
        if not (phone_number and password):
            return None

        user = get_user_model().objects.filter(phone_number=phone_number).first()
        return self.check_credentials(user, password)
