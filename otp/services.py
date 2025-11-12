from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import EmailOTP, PhoneNumberOTP


class OTPService:
    """
    Handles OTP creation, update, and verification for both email and phone.
    """

    model_map = {
        'email': EmailOTP,
        'phone': PhoneNumberOTP,
    }

    @classmethod
    def get_user(cls, field, value):
        user_model = get_user_model()
        try:
            return user_model.objects.active().get(**{field: value})
        except user_model.DoesNotExist:
            raise ValidationError(_(f'User with that {field.replace("_", " ")} does not exist'))

    @classmethod
    def request_otp(cls, channel, user, contact_value, purpose):
        """
        Get or create OTP record and generate a verification token.
        """
        model = cls.model_map[channel]
        lookup_field = 'email' if channel == 'email' else 'phone_number'

        otp, created = model.objects.get_or_create(
            user=user,
            defaults={lookup_field: contact_value}
        )

        # Sync updated contact info if changed
        if not created and getattr(otp, lookup_field) != contact_value:
            setattr(otp, lookup_field, contact_value)
            otp.save(update_fields=[lookup_field])

        success, details = otp.generate_verification(purpose=purpose)
        if not success:
            raise ValidationError({"non_field_errors": [details["reason"]]})

        return otp

    @classmethod
    def confirm_otp(cls, channel, request_id, token, purpose):
        """
        Verify an OTP by request ID and token.
        """
        model = cls.model_map[channel]
        try:
            otp = model.objects.get(request_id=request_id)
        except model.DoesNotExist:
            raise ValidationError({"request_id": _("Invalid or expired verification request.")})

        success, details = otp.verify(purpose, token)
        if not success:
            raise ValidationError(details["reason"])

        return otp
