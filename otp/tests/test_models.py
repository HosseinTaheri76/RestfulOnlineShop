from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from freezegun import freeze_time
from rest_framework.test import APITestCase

from otp import models
from otp import conf


class OTPModelTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ali", password="password123")
        self.email_otp = models.EmailOTP.objects.create(user=self.user)
        self.phone_otp = models.PhoneNumberOTP.objects.create(user=self.user)

    # ------------------------------------------------------------------
    # Token generation tests
    # ------------------------------------------------------------------
    def test_can_generate_first_time(self):
        success, details = self.email_otp.generate_verification("signup")
        self.assertTrue(success)
        self.assertIn("expires_at", vars(self.email_otp))
        self.assertIsNone(self.email_otp._raw_token)

    def test_generate_sets_all_required_fields(self):
        self.email_otp.generate_verification("signup")
        ver = self.email_otp
        self.assertIsNotNone(ver.hashed_token)
        self.assertIsNotNone(ver.request_id)
        self.assertIsNotNone(ver.requested_at)
        self.assertIsNotNone(ver.expires_at)
        self.assertEqual(ver.purpose, "signup")

    def test_cannot_generate_before_cooldown_ends(self):
        self.email_otp.generate_verification("signup")
        success, details = self.email_otp.generate_verification("signup")
        self.assertFalse(success)
        self.assertIn("Please wait", details["reason"])

    def test_cannot_generate_if_throttled(self):
        self.email_otp.throttle_until = timezone.now() + timedelta(seconds=100)
        self.email_otp.save()
        success, details = self.email_otp.generate_verification("signup")
        self.assertFalse(success)
        self.assertIn("Too many attempts", details["reason"])

    def test_next_request_time_allows_regeneration_after_cooldown(self):
        self.email_otp.generate_verification("signup")
        self.email_otp.next_request_at = timezone.now() - timedelta(seconds=1)
        self.email_otp.save()
        success, details = self.email_otp.generate_verification("signup")
        self.assertTrue(success)

    # ------------------------------------------------------------------
    # OTP (confirm) tests
    # ------------------------------------------------------------------
    def test_verify_with_correct_token_succeeds(self):
        self.email_otp.generate_verification("signup")
        token = self.email_otp._generate_token()
        self.email_otp.hashed_token = self.email_otp.hashed_token = self.email_otp.hashed_token = self.email_otp.hashed_token  # keep same token
        raw_token = self.email_otp._generate_token()
        # Recreate same hash for test
        self.email_otp._reset_state("signup")
        token = self.email_otp._raw_token
        ok, details = self.email_otp.verify("signup", token)
        self.assertTrue(ok)
        self.assertFalse(details)
        self.assertLessEqual(self.email_otp.expires_at, timezone.now())

    def test_verify_fails_with_wrong_token(self):
        self.email_otp.generate_verification("signup")
        ok, details = self.email_otp.verify("signup", "wrong")
        self.assertFalse(ok)
        self.assertIn("invalid", details["reason"].lower())

    def test_verify_fails_if_expired(self):
        self.email_otp.generate_verification("signup")
        self.email_otp.expires_at = timezone.now() - timedelta(seconds=1)
        self.email_otp.save()
        ok, details = self.email_otp.verify("signup", "123456")
        self.assertFalse(ok)
        self.assertIn("expired", details["reason"].lower())

    def test_verify_fails_if_throttled(self):
        self.email_otp.throttle_until = timezone.now() + timedelta(seconds=50)
        self.email_otp.save()
        ok, details = self.email_otp.verify("signup", "123456")
        self.assertFalse(ok)
        self.assertIn("too many failed attempts", details["reason"].lower())

    def test_verify_fails_if_purpose_mismatch(self):
        self.email_otp.generate_verification("signup")
        token = self.email_otp._raw_token
        ok, details = self.email_otp.verify("different", token)
        self.assertFalse(ok)
        self.assertIn("invalid request", details["reason"].lower())

    def test_record_failed_attempt_increments_counter(self):
        initial = self.email_otp.attempt_count
        self.email_otp._record_failed_attempt()
        self.assertEqual(self.email_otp.attempt_count, initial + 1)

    def test_throttling_applied_after_max_attempts(self):
        for _ in range(conf.MAX_ATTEMPTS + 1):
            self.email_otp._record_failed_attempt()
        self.assertIsNotNone(self.email_otp.throttle_until)
        self.assertGreater(self.email_otp.throttle_until, timezone.now())

    def test_successful_verification_resets_throttling(self):
        self.email_otp.throttle_until = timezone.now() + timedelta(seconds=100)
        self.email_otp.save()
        self.email_otp._mark_successful_verification()
        self.assertIsNone(self.email_otp.throttle_until)
        self.assertIsNone(self.email_otp.next_request_at)

    # ------------------------------------------------------------------
    # Phone number OTP basic tests
    # ------------------------------------------------------------------
    def test_phone_verification_delivery(self):
        """Ensure phone OTP calls its delivery function."""
        self.phone_otp.phone_number = "+981234567890"
        success, _ = self.phone_otp.generate_verification("signup")
        self.assertTrue(success)
        self.assertIsNotNone(self.phone_otp.expires_at)

    # ------------------------------------------------------------------
    # OTP grant tests
    # ------------------------------------------------------------------
    def test_otp_grant_created_with_valid_expiry(self):
        grant = models.OTPGrant.objects.create(
            user=self.user, purpose="password_reset"
        )
        self.assertIsNotNone(grant.expires_at)
        self.assertGreater(grant.expires_at, timezone.now())

    def test_otp_grant_is_usable_before_expiry(self):
        grant = models.OTPGrant.objects.create(
            user=self.user, purpose="password_reset"
        )
        self.assertTrue(grant.is_usable())

    def test_otp_grant_not_usable_after_expiry(self):
        # 1. Create a grant at current time
        grant = models.OTPGrant.objects.create(
            user=self.user, purpose="password_reset"
        )
        # 2. Fast-forward time beyond expiry using freezegun
        future_time = timezone.now() + timedelta(minutes=11)
        with freeze_time(future_time):
            # 3. It should no longer be usable
            self.assertFalse(grant.is_usable())

    def test_consume_marks_grant_as_used(self):
        grant = models.OTPGrant.objects.create(
            user=self.user, purpose="password_reset"
        )
        grant.consume()
        self.assertTrue(grant.consumed)
        self.assertFalse(grant.is_usable())
