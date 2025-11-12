from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from phonenumber_field.serializerfields import PhoneNumberField

from .services import OTPService
from .models import OTPGrant


class BaseOTPSerializer(serializers.Serializer):
    _user = None

    @property
    def _purpose(self):
        return self.context.get('purpose')

    def to_representation(self, instance):
        return {
            "request_id": str(instance.request_id),
            "expires_at": instance.expires_at,
        }


# ---------- Shared Confirm Serializer ----------

class OTPConfirmSerializer(serializers.Serializer):
    """
    Base serializer for confirming an OTP and issuing a temporary permission (grant).
    """

    otp_channel = None
    request_id = serializers.UUIDField(label=_("Request ID"), write_only=True)
    token = serializers.CharField(label=_("Token"), write_only=True)

    def validate(self, attrs):
        otp = OTPService.confirm_otp(
            channel=self.otp_channel,
            request_id=attrs["request_id"],
            token=attrs["token"],
            purpose=self.context.get("purpose"),
        )

        # Automatically issue an OTP grant
        grant = OTPGrant.objects.create(
            user=otp.user,
            purpose=otp.purpose,
        )

        # Attach for to_representation and DRF context
        self.instance = grant
        return attrs

    def to_representation(self, instance):
        return {
            "grant_id": str(instance.pk),
            "expires_at": instance.expires_at,
        }


# ---------- Email OTP Serializers ----------

class EmailOTPRequestSerializer(BaseOTPSerializer):
    email = serializers.EmailField(label=_('Email'), write_only=True)

    def validate(self, attrs):
        email = attrs['email']
        user = OTPService.get_user('email', email)
        self._user = user
        otp = OTPService.request_otp('email', user, email, self._purpose)
        self.instance = otp
        return attrs


class EmailOTPConfirmSerializer(OTPConfirmSerializer):
    otp_channel = 'email'


# ---------- Phone Number OTP Serializers ----------

class PhoneNumberOTPRequestSerializer(BaseOTPSerializer):
    phone_number = PhoneNumberField(label=_("Phone number"), write_only=True, region="IR")

    def validate(self, attrs):
        phone_number = attrs['phone_number']
        user = OTPService.get_user('phone_number', phone_number)
        self._user = user
        otp = OTPService.request_otp('phone', user, phone_number, self._purpose)
        self.instance = otp
        return attrs


class PhoneNumberOTPConfirmSerializer(OTPConfirmSerializer):
    otp_channel = 'phone'
