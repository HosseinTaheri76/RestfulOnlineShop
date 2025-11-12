from uuid import uuid4
from random import randint
from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.hashers import make_password, check_password
from phonenumber_field.modelfields import PhoneNumberField

from . import conf

class AbstractOTP(models.Model):
    """
    Abstract base for OTP (email/phone).
    Handles token lifecycle, cooldowns, throttling, and attempts.
    """
    _raw_token = None  # stored in memory only, never saved

    user = models.OneToOneField(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s",
        verbose_name=_("user"),
    )
    request_id = models.UUIDField(
        verbose_name=_("request ID"),
        unique=True,
        null=True,
        blank=True
    )
    purpose = models.CharField(
        verbose_name=_("purpose"),
        max_length=128,
        null=True,
        blank=True
    )
    hashed_token = models.CharField(
        verbose_name=_("hashed token"),
        max_length=128,
        null=True,
        blank=True
    )
    requested_at = models.DateTimeField(
        verbose_name=_("requested at"),
        null=True,
        blank=True
    )
    expires_at = models.DateTimeField(
        verbose_name=_("expires at"),
        null=True,
        blank=True
    )
    last_attempt_at = models.DateTimeField(
        verbose_name=_("last attempt at"),
        null=True,
        blank=True
    )
    attempt_count = models.PositiveIntegerField(
        verbose_name=_("attempt count"),
        default=0
    )
    next_request_at = models.DateTimeField(
        verbose_name=_("next request at"),
        null=True,
        blank=True
    )
    throttle_until = models.DateTimeField(
        verbose_name=_("throttle until"),
        null=True,
        blank=True
    )

    class Meta:
        abstract = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _deliver_token(self, token: str):
        """Must be implemented by subclasses (e.g., send email or SMS)."""
        raise NotImplementedError

    @staticmethod
    def _generate_token() -> str:
        """Generate a numeric token of configured length."""
        min_val = 10 ** (conf.TOKEN_LENGTH - 1)
        max_val = (10 ** conf.TOKEN_LENGTH) - 1
        return str(randint(min_val, max_val))

    # ------------------------------------------------------------------
    # Token lifecycle
    # ------------------------------------------------------------------
    def _reset_state(self, purpose: str):
        """Reset the verification state and prepare for a new token."""
        now = timezone.now()
        token = self._generate_token()

        self._raw_token = token
        self.hashed_token = make_password(token)
        self.purpose = purpose
        self.request_id = uuid4()
        self.requested_at = now
        self.expires_at = now + timedelta(seconds=conf.TOKEN_LIFETIME_SECONDS)
        self.next_request_at = now + timedelta(seconds=conf.REQUEST_COOLDOWN_SECONDS)
        self.attempt_count = 0
        self.last_attempt_at = None
        self.throttle_until = None

        self.save()

    def _record_failed_attempt(self):
        """Increment attempts and apply throttling if the limit exceeded."""
        now = timezone.now()

        self.attempt_count += 1
        self.last_attempt_at = now

        if self.attempt_count > conf.MAX_ATTEMPTS:
            self.throttle_until = now + timedelta(seconds=conf.THROTTLE_SECONDS)

        self.save(update_fields=["attempt_count", "last_attempt_at", "throttle_until"])

    def _mark_successful_verification(self):
        """Mark token as used and lift restrictions."""
        self.throttle_until = None
        self.next_request_at = None
        self.expires_at = timezone.now()
        self.save(update_fields=["expires_at", "next_request_at", "throttle_until"])

    # ------------------------------------------------------------------
    # State checks
    # ------------------------------------------------------------------
    def _can_generate(self):
        """Return (bool, details) whether a new request can be made."""
        now = timezone.now()

        if self.throttle_until and self.throttle_until > now:
            remaining = int((self.throttle_until - now).total_seconds())
            return False, {"reason": _("Too many attempts. Try again in %(s)s seconds.") % {"s": remaining}}

        if self.next_request_at and self.next_request_at > now:
            remaining = int((self.next_request_at - now).total_seconds())
            return False, {"reason": _("Please wait %(s)s seconds before requesting again.") % {"s": remaining}}

        return True, {}

    def _can_verify(self):
        """Return (bool, details) whether verification can be attempted."""
        now = timezone.now()

        if self.throttle_until and self.throttle_until > now:
            remaining = int((self.throttle_until - now).total_seconds())
            return False, {"reason": _("Too many failed attempts. Try again in %(s)s seconds.") % {"s": remaining}}

        return True, {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate_verification(self, purpose: str):
        """Generate and deliver a new verification token."""
        allowed, details = self._can_generate()

        if not allowed:
            return False, details

        self._reset_state(purpose)
        self._deliver_token(self._raw_token)
        self._raw_token = None  # Never store token in memory beyond delivery

        return True, details

    def verify(self, purpose: str, raw_token: str):
        """Verify the provided token and optionally create a temporary permission."""
        allowed, details = self._can_verify()

        if not allowed:
            return False, details

        if purpose != self.purpose:
            self._record_failed_attempt()
            return False, {"reason": _("Invalid request.")}

        if not self.expires_at or self.expires_at <= timezone.now():
            self._record_failed_attempt()
            return False, {"reason": _("The code is invalid or has expired.")}

        if not check_password(raw_token, self.hashed_token):
            self._record_failed_attempt()
            return False, {"reason": _("The code is invalid or has expired.")}

        self._mark_successful_verification()

        return True, details

class OTPGrant(models.Model):
    """Represents a short-lived permission granted after successful verification."""

    id = models.UUIDField(
        verbose_name=_("id"),
        primary_key=True,
        default=uuid4,
        editable=False
    )
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="temporary_permissions",
        verbose_name=_("user"),
    )
    purpose = models.CharField(
        verbose_name=_("purpose"),
        max_length=255
    )
    consumed = models.BooleanField(
        verbose_name=_("consumed"),
        default=False
    )
    created_at = models.DateTimeField(
        verbose_name=_("created at"),
        auto_now_add=True
    )
    expires_at = models.DateTimeField(
        verbose_name=_("expires at")
    )

    def is_usable(self):
        return not self.consumed and self.expires_at > timezone.now()

    def consume(self):
        """Mark permission as used."""
        if not self.consumed:
            self.consumed = True
            self.save(update_fields=["consumed"])

    def save(self, *args, **kwargs):
        if self.expires_at is None:
            self.expires_at = timezone.now() + timedelta(seconds=conf.TEMPORARY_PERMISSIONS_LIFETIME_SECONDS)
        super().save(*args, **kwargs)

# ---------------------------------------------------------------------
# Concrete Implementations
# ---------------------------------------------------------------------
class EmailOTP(AbstractOTP):
    email = models.EmailField(
        verbose_name=_("email"),
        null=True,
        blank=True
    )

    def _deliver_token(self, token: str):
        email = self.email or getattr(self.user, "email", None)
        print(f"Delivering token {token} to {email}")
        # You could integrate actual sending logic here (e.g., Celery task).


class PhoneNumberOTP(AbstractOTP):
    phone_number = PhoneNumberField(
        verbose_name=_("phone number"),
        null=True,
        blank=True,
        region="IR"
    )

    def _deliver_token(self, token: str):
        number = self.phone_number or getattr(self.user, "phone_number", None)
        print(f"Delivering token {token} to {number}")
        # Real implementation would use an SMS provider API.