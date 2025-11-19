from django.contrib.auth.models import AbstractUser, UserManager
from django.utils.translation import gettext_lazy as _
from django.db import models

from phonenumber_field.modelfields import PhoneNumberField


class CustomUserManager(UserManager):

    def normalize_email(self, email):
        return super().normalize_email(email) or None

    def active(self):
        return self.get_queryset().filter(is_active=True)


class User(AbstractUser):
    email = models.EmailField(
        _('email address'),
        unique=True,
        null=True,
        blank=True,
    )
    email_verified = models.BooleanField(
        _('email verified'),
        default=False,
    )
    phone_number = PhoneNumberField(
        _('phone number'),
        unique=True,
        null=True,
        blank=True,
        region='IR'
    )
    phone_number_verified = models.BooleanField(
        _('phone number verified'),
        default=False,
    )

    objects = CustomUserManager()

    def get_usable_email(self):
        if self.email and self.email_verified:
            return self.email
        return None

    def get_usable_phone_number(self):
        if self.phone_number and self.phone_number_verified:
            return self.phone_number
        return None
