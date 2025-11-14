from django.contrib.auth import password_validation, authenticate
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _
from phonenumber_field.serializerfields import PhoneNumberField

from rest_framework import serializers
from phonenumber_field.phonenumber import PhoneNumber
from phonenumbers.phonenumberutil import NumberParseException
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from otp.services import OTPService


def is_valid_email(value: str) -> bool:
    try:
        validate_email(value)
        return True
    except ValidationError:
        return False


def is_valid_phone_number(value: str) -> bool:
    try:
        return PhoneNumber.from_string(value, region="IR").is_valid()
    except NumberParseException:
        return False


class UserCreateSerializer(serializers.ModelSerializer):
    email_or_phone_number = serializers.CharField(
        label=_("Email or Phone Number"),
        write_only=True,
        source="username",
    )
    password1 = serializers.CharField(
        label=_("Password"),
        write_only=True,
        style={"input_type": "password"},
        validators=[password_validation.validate_password],
        help_text=password_validation.password_validators_help_text_html,
    )
    password2 = serializers.CharField(
        label=_("Password confirmation"),
        write_only=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email_or_phone_number",
            "password1",
            "password2",
            "email",
            "email_verified",
            "phone_number",
            "phone_number_verified",
            "first_name",
            "last_name",
        )
        read_only_fields = (
            "id",
            "email",
            "email_verified",
            "phone_number",
            "phone_number_verified",
            "first_name",
            "last_name",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._email = None
        self._phone_number = None

    # ---------------------------
    # Field-level validation
    # ---------------------------
    def validate_email_or_phone_number(self, value):
        if is_valid_email(value):
            if User.objects.filter(email__iexact=value).exists():
                raise serializers.ValidationError(
                    _("A user with this email already exists.")
                )
            self._email = value
        elif is_valid_phone_number(value):
            if User.objects.filter(phone_number=value).exists():
                raise serializers.ValidationError(
                    _("A user with this phone number already exists.")
                )
            self._phone_number = value
        else:
            raise serializers.ValidationError(
                _("Please enter a valid email address or phone number.")
            )
        return value

    # ---------------------------
    # Object-level validation
    # ---------------------------
    def validate(self, attrs):
        if attrs["password1"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password2": _("The two passwords didn't match.")}
            )
        return attrs

    # ---------------------------
    # Create method
    # ---------------------------
    def create(self, validated_data):
        validated_data.pop("password2")
        validated_data["password"] = validated_data.pop("password1")
        validated_data["email"] = self._email
        validated_data["phone_number"] = self._phone_number
        return User.objects.create_user(**validated_data)


class PasswordLoginSerializer(serializers.Serializer):
    email_or_phone_number = serializers.CharField(
        label=_("Email or Phone Number"),
        write_only=True,
    )
    password = serializers.CharField(
        label=_("Password"),
        write_only=True,
    )

    @property
    def request(self):
        return self.context.get("request")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user, self.email, self.phone_number = None, None, None

    def validate_email_or_phone_number(self, value):
        if is_valid_email(value):
            self.email = value
            return value
        elif is_valid_phone_number(value):
            self.phone_number = value
            return value
        raise serializers.ValidationError(_('Please enter a valid email address or phone number.'))

    def validate(self, attrs):
        self.user = authenticate(
            request=self.request,
            email=self.email,
            phone_number=self.phone_number,
            password=attrs.get("password"),
        )
        return attrs

    def to_representation(self, instance):
        refresh = RefreshToken.for_user(self.user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class OTPLoginConfirmSerializer(serializers.Serializer):
    request_id = serializers.UUIDField(label=_("Request ID"), write_only=True)
    token = serializers.CharField(label=_("Verification token"), write_only=True)

    @property
    def request(self):
        return self.context.get("request")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None

    def validate(self, attrs):
        request_id = attrs.get("request_id")
        token = attrs.get("token")
        self.user = authenticate(
            request=self.request,
            request_id=request_id,
            token=token,
        )
        return attrs

    def to_representation(self, instance):
        refresh = RefreshToken.for_user(self.user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class RequestEmailChangeSerializer(serializers.Serializer):
    _purpose = 'change-email'

    email = serializers.EmailField(label=_("Email"))

    @property
    def user(self):
        return self.context.get("request").user

    @staticmethod
    def validate_email(value):
        if User.objects.filter(email__iexact=value).exists():
            # either entering his current email or another ones email
            raise serializers.ValidationError(_("A user with this email already exists."))
        return value

    def validate(self, attrs):
        email = attrs["email"]
        otp = OTPService.request_otp('email', self.user, email, self._purpose)
        self.instance = otp
        return attrs

    def to_representation(self, instance):
        return {
            "request_id": str(instance.request_id),
            "expires_at": instance.expires_at,
        }


class RequestPhoneChangeSerializer(serializers.Serializer):
    _purpose = 'change-phone'

    phone = PhoneNumberField(label=_("Phone number"), write_only=True, region="IR")

    @property
    def user(self):
        return self.context.get("request").user

    @staticmethod
    def validate_phone(value):
        if User.objects.filter(phone_number=value).exists():
            # either entering his current phone or another ones phone
            raise serializers.ValidationError(_("A user with this phone number already exists."))
        return value

    def validate(self, attrs):
        phone = attrs["phone"]
        otp = OTPService.request_otp('phone', self.user, phone, self._purpose)
        self.instance = otp
        return attrs

    def to_representation(self, instance):
        return {
            "request_id": str(instance.request_id),
            "expires_at": instance.expires_at,
        }

class PasswordResetSerializer(serializers.Serializer):
    password1 = serializers.CharField(
        label=_("Password"),
        write_only=True,
        style={"input_type": "password"},
        validators=[password_validation.validate_password],
        help_text=password_validation.password_validators_help_text_html,
    )
    password2 = serializers.CharField(
        label=_("Password confirmation"),
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        if attrs["password1"] != attrs["password2"]:
            raise serializers.ValidationError(_("The two passwords didn't match."))
        return attrs

    def update(self, instance, validated_data):
        instance.set_password(validated_data["password1"])
        instance.save(update_fields=["password"])
        return instance

class PasswordChangeSerializer(serializers.Serializer):

    old_password = serializers.CharField(
        label=_("Old password"),
        write_only=True,
        style={"input_type": "password"}
    )
    new_password1 = serializers.CharField(
        label=_("New password"),
        write_only=True,
        style={"input_type": "password"},
        validators = [password_validation.validate_password],
        help_text = password_validation.password_validators_help_text_html,
    )
    new_password2 = serializers.CharField(
        label=_("New password"),
        write_only=True,
        style={"input_type": "password"}
    )

    def validate_old_password(self, value):
        if not self.instance.check_password(value):
            raise serializers.ValidationError(_("Old password incorrect."))
        return value

    def validate(self, attrs):
        if attrs["new_password1"] != attrs["new_password2"]:
            raise serializers.ValidationError(_("The two passwords didn't match."))
        return attrs

    def update(self, instance, validated_data):
        instance.set_password(validated_data["new_password1"])
        instance.save()
        return instance