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
    """
    Stores user's addresses with validation ensuring:
    - City belongs to the chosen province
    - Valid postal code (optional, but must be 10 digits if present)
    - Recipient name & phone auto-filled from user if missing
    - Exactly one default address per user
    - Default address cannot be reassigned to another user
    """

    # --------------------
    # Basic Fields
    # --------------------
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name=_("user"),
    )
    title = models.CharField(
        _("title"),
        max_length=55,
        help_text=_("Example: Home, Work, Office."),
    )
    recipient_full_name = models.CharField(
        _("recipient full name"),
        max_length=128,
        blank=True,
        help_text=_("Defaults to user's full name if left blank."),
    )
    recipient_phone = PhoneNumberField(
        _("recipient phone number"),
        blank=True,
        region="IR",
        help_text=_("Defaults to user's phone number if left blank."),
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

    street = models.CharField(_("street"), max_length=255)
    address_line_2 = models.CharField(
        _("additional address info"),
        max_length=255,
        blank=True,
    )

    building_number = models.PositiveSmallIntegerField(_("building number"))
    unit_number = models.PositiveSmallIntegerField(
        _("unit number"),
        blank=True,
        null=True,
    )

    postal_code = models.CharField(
        _("postal code"),
        max_length=10,
        blank=True,
    )

    is_default = models.BooleanField(
        _("default address"),
        default=False,
    )

    # Track user_id & is_default changes
    _tracker = FieldTracker(fields=["user_id", "is_default"])

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ("-is_default", "id")
        unique_together = (
            ("user", "title"),
            ("user", "postal_code"),
        )

    def __str__(self):
        return f"{self.user} – {self.title}"

    # -----------------------------------------
    # Save
    # -----------------------------------------
    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.user:
            self.handle_is_default()
        super().save(*args, **kwargs)

    # -----------------------------------------
    # Clean & Validation
    # -----------------------------------------
    def clean(self):
        """
        Performs full object validation:
        - Fills missing recipient info
        - Ensures required data exists
        - Collects all errors instead of raising early
        """
        errors = {}

        # Run parent's clean() first
        try:
            super().clean()
        except ValidationError as e:
            errors.update(e.message_dict)

        # Auto-fill recipient info
        self.recipient_full_name = (
                self.recipient_full_name or self.user.get_full_name()
        )
        self.recipient_phone = (
                self.recipient_phone or self.user.get_usable_phone_number()
        )

        # Validate missing fallback data
        if not self.recipient_full_name:
            errors["recipient_full_name"] = _(
                "Recipient full name is empty and cannot be derived from the user's profile."
            )

        if not self.recipient_phone:
            errors["recipient_phone"] = _(
                "Recipient phone number is empty and the user has no registered phone number."
            )

        if errors:
            raise ValidationError(errors)

    # -------------------------------
    # Custom Validation Methods
    # -------------------------------
    @skip_if_missing_fields("province", "city")
    def _validate_city_belongs_to_province(self):
        """Ensures city is part of the selected province."""
        if self.city.province_id != self.province_id:
            raise ValidationError({
                "city": _(
                    "The selected city does not belong to the chosen province."
                )
            })

    def _validate_postal_code(self):
        """Postal code must be exactly 10 digits if provided."""
        if self.postal_code:
            if not self.postal_code.isdigit() or len(self.postal_code) != 10:
                raise ValidationError({
                    "postal_code": _(
                        "Postal code must consist of exactly 10 numeric digits."
                    )
                })

    def _validate_user(self):
        """
        Prevent changing the user of a default address.
        """
        if (
                self._tracker.has_changed("user_id")
                and self._tracker.previous("is_default")
        ):
            raise ValidationError({
                "user": _(
                    "You cannot reassign a default address to another user."
                )
            })

    # -----------------------------------------
    # Default Address Handling
    # -----------------------------------------
    def handle_is_default(self):
        """
        Ensures:
        - Only one default address exists per user.
        - If no default exists, the new address becomes default.
        - If this address becomes default, all others are unset.
        """
        if not self.user:
            return

        qs = self.user.addresses.all()

        # Exclude current instance if updating
        if self.pk:
            qs = qs.exclude(pk=self.pk)

        # If this is set as default -> unset all others
        if self.is_default:
            qs.select_for_update().update(is_default=False)
            return

        # If user has no default address -> force this default
        if not qs.filter(is_default=True).exists():
            self.is_default = True

    def to_dict(self):
        return {
            'title': self.title,
            'recipient_full_name': self.recipient_full_name,
            'recipient_phone': self.recipient_phone,
            'province': self.province,
            'city': self.city,
            'street': self.street,
            'address_line_2': self.address_line_2,
            'building_number': self.building_number,
            'unit_number': self.unit_number,
            'postal_code': self.postal_code,
            'is_default': self.is_default,
        }
