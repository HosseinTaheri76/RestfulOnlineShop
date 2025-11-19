from django.db import models
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from model_utils.tracker import FieldTracker
from phonenumber_field.modelfields import PhoneNumberField

from locations.models import Province, City
from utils.models.validation import ModelValidationMixin, skip_if_missing_fields


class UserAddress(ModelValidationMixin, models.Model):

    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name=_("user"),
    )
    title = models.CharField(
        verbose_name=_("title"),
        max_length=55,
        help_text=_("Home for example."),
    )
    recipient_full_name = models.CharField(
        blank=True,
        max_length=128,
        verbose_name=_("recipient full name"),
        help_text=_('Defaults to user fullname if left blank.'),
    )
    recipient_phone = PhoneNumberField(
        blank=True,
        region='IR',
        verbose_name=_("recipient phone number"),
        help_text=_('Defaults to user phone number if left blank.'),
    )
    province = models.ForeignKey(
        to=Province,
        on_delete=models.PROTECT,
        related_name="user_addresses",
        verbose_name=_("province"),
    )
    city = models.ForeignKey(
        to=City,
        on_delete=models.PROTECT,
        related_name="user_addresses",
        verbose_name=_("city"),
    )
    street = models.CharField(
        max_length=255,
        verbose_name=_("street"),
    )
    address_line_2 = models.CharField(
        blank=True,
        max_length=255,
        verbose_name=_("additional address info"),
    )
    building_number = models.PositiveSmallIntegerField(
        verbose_name=_("building number")
    )
    unit_number = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        verbose_name=_("unit number"),
    )
    postal_code = models.CharField(
        blank=True,
        max_length=10,
        verbose_name=_("postal code"),
    )
    is_default = models.BooleanField(
        verbose_name=_("default address"),
        default=False
    )

    _tracker = FieldTracker(fields=['is_default'])

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ("-is_default", "id")
        unique_together = (("user", "title"), ("user", "postal_code"))

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.user:
            self.handle_is_default()
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}

        try:
            super().clean()
        except ValidationError as e:
            errors.update(e.message_dict)

        self.recipient_phone = self.recipient_phone or self.user.phone_number
        self.recipient_full_name = self.recipient_full_name or self.user.get_full_name()

        if not self.recipient_phone:
            errors["recipient_phone"] = _("Recipient phone number is empty and the user has no phone number.")

        if not self.recipient_full_name:
            errors["recipient_full_name"] = _("Recipient full name is empty and the user profile has no full name.")

        if errors:
            raise ValidationError(errors)

    # ---------------------
    # Validation Methods
    # ---------------------
    @skip_if_missing_fields("province", "city")
    def _validate_city_belongs_to_province(self):
        if self.city.province_id != self.province_id:
            raise ValidationError({
                "city": _("Selected city does not belong to selected province.")
            })

    def _validate_postal_code(self):
        if self.postal_code:
            if not self.postal_code.isdigit() or len(self.postal_code) != 10:
                raise ValidationError({
                    "postal_code": _("Postal code must be exactly 10 digits.")
                })

    # ---------------------
    # Default Address Logic
    # ---------------------
    def handle_is_default(self):
        """Ensures only one default address per user."""

        user_addresses = self.user.addresses

        if self.pk:  # Existing address
            if self._tracker.has_changed("is_default"):
                if self.is_default:
                    # Set others to False
                    user_addresses.exclude(pk=self.pk).update(is_default=False)
                else:
                    # Prevent turning off the only default
                    if not user_addresses.exclude(pk=self.pk).filter(is_default=True).exists():
                        self.is_default = True
        else:  # New address
            if self.is_default:
                user_addresses.update(is_default=False)
            else:
                if not user_addresses.exists():
                    self.is_default = True
