from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from django.contrib.auth.hashers import make_password
from django.test import TestCase

from rest_framework import serializers

from otp.models import EmailOTP, PhoneNumberOTP
from otp import serializers

User = get_user_model()


class RequestOTPSerializerTests(TestCase):
    def setUp(self):
        self.user_email = User.objects.create_user(username="user1", email="user@example.com")
        self.user_phone = User.objects.create_user(username="user2", phone_number="+989123456789")

    def test_raises_error_if_user_not_found(self):
        non_existent_email = 'test@test.com'
        non_existent_phone_number = '+989123380176'

        kwargs = {'data': {'email': non_existent_email}, 'context': {'purpose': 'login'}}
        serializer = serializers.EmailOTPRequestSerializer(**kwargs)
        with self.assertRaises(ValidationError) as exc:
            serializer.is_valid(raise_exception=True)
        self.assertIn('User with that email does not exist', str(exc.exception))

        kwargs = {'data': {'phone_number': non_existent_phone_number}, 'context': {'purpose': 'login'}}
        serializer = serializers.PhoneNumberOTPRequestSerializer(**kwargs)
        with self.assertRaises(ValidationError) as exc:
            serializer.is_valid(raise_exception=True)
        self.assertIn('User with that phone number does not exist', str(exc.exception))

    @patch("otp.models.EmailOTP._deliver_token")
    def test_generate_OTP_success_for_email(self, mock_deliver):
        serializer = serializers.EmailOTPRequestSerializer(
            data={"email": "user@example.com"},
            context={"purpose": "login"},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.instance
        self.assertIsInstance(instance, EmailOTP)
        self.assertEqual(instance.user, self.user_email)
        mock_deliver.assert_called_once()  # token should be sent

    @patch("otp.models.PhoneNumberOTP._deliver_token")
    def test_generate_verification_success_for_phone(self, mock_deliver):
        serializer = serializers.PhoneNumberOTPRequestSerializer(
            data={"phone_number": "+989123456789"},
            context={"purpose": "login"},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.instance
        self.assertIsInstance(instance, PhoneNumberOTP)
        self.assertEqual(instance.user, self.user_phone)
        mock_deliver.assert_called_once()

    @patch("otp.models.EmailOTP.generate_verification")
    def test_generate_OTP_failure_raises_error(self, mock_generate):
        mock_generate.return_value = (False, {"reason": "Rate limited"})
        serializer = serializers.EmailOTPRequestSerializer(
            data={"email": "user@example.com"},
            context={"purpose": "login"},
        )
        with self.assertRaises(ValidationError) as exc:
            serializer.is_valid(raise_exception=True)
        self.assertIn("Rate limited", str(exc.exception))

class ConfirmOTPSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user3", email="verify@example.com")
        self.otp = EmailOTP.objects.create(user=self.user)
        # Simulate a request already generated
        self.otp._reset_state("login")

    def test_validation_successful_otp(self):
        token = self.otp._generate_token()
        self.otp.hashed_token = make_password(token)
        self.otp.purpose = "login"
        self.otp.save()

        # Patch verify() method to simulate success
        with patch.object(EmailOTP, "verify", return_value=(True, {})) as mock_verify:
            serializer = serializers.EmailOTPConfirmSerializer(
                data={
                    "request_id": str(self.otp.request_id),
                    "token": "123456",
                },
                context={"purpose": "login"},
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            mock_verify.assert_called_once()

    def test_invalid_request_id_raises_error(self):
        serializer = serializers.EmailOTPConfirmSerializer(
            data={
                "request_id": str(uuid4()),
                "token": "123456",
            },
            context={"purpose": "login"},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("Invalid or expired", str(serializer.errors))

    @patch.object(EmailOTP, "verify", return_value=(False, {"reason": "Expired"}))
    def test_invalid_token_raises_error(self, mock_verify):
        serializer = serializers.EmailOTPConfirmSerializer(
            data={
                "request_id": str(self.otp.request_id),
                "token": "wrong",
            },
            context={"purpose": "login"},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("Expired", str(serializer.errors))
