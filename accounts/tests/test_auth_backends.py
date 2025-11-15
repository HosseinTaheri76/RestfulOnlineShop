from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed

from accounts import auth_backends


class AuthenticationBackendTestCase(TestCase):

    def setUp(self):
        self.username = 'test-user'
        self.email = 'test@test.com'
        self.phone_number = '+989120000000'
        self.password = 'password123'
        self.user = get_user_model().objects.create_user(
            username=self.username,
            email=self.email,
            phone_number=self.phone_number,
            password=self.password,
        )


class TestEmailPasswordBackend(AuthenticationBackendTestCase):
    backend = auth_backends.EmailPasswordBackend()

    def test_authenticate_success(self):
        user = self.backend.authenticate(
            request=None,
            email=self.email,
            password=self.password
        )
        self.assertEqual(user, self.user)

    def test_authenticate_with_invalid_credentials(self):
        with self.assertRaises(AuthenticationFailed):
            self.backend.authenticate(request=None, email="user@example.com", password="WrongPass")

    def test_authenticate_with_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(AuthenticationFailed):
            self.backend.authenticate(request=None, email=self.email, password=self.password)


class TestPhonePasswordBackend(AuthenticationBackendTestCase):
    backend = auth_backends.PhonePasswordBackend()

    def test_authenticate_success(self):
        user = self.backend.authenticate(
            request=None,
            phone_number=self.phone_number,
            password=self.password
        )
        self.assertEqual(user, self.user)

    def test_authenticate_with_invalid_credentials(self):
        with self.assertRaises(AuthenticationFailed):
            self.backend.authenticate(request=None, phone_number="+989301111101", password="WrongPass")

    def test_authenticate_with_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(AuthenticationFailed):
            self.backend.authenticate(request=None, phone_number=self.phone_number, password=self.password)


class TestEmailOTPBackend(AuthenticationBackendTestCase):
    backend = auth_backends.EmailOTPBackend()

    def test_authenticate_successful_verification(self):
        verification_mock = MagicMock()
        verification_mock.user = self.user
        verification_mock.verify.return_value = (True, {})

        with patch.object(self.backend, "otp_model", MagicMock()) as mock_model:
            mock_model.objects.get.return_value = verification_mock
            result = self.backend.authenticate(
                request=None,
                request_id="abc123",
                token="9999",
            )

        self.assertEqual(result, self.user)
        verification_mock.verify.assert_called_once_with(purpose="login", raw_token="9999")

    def test_authenticate_with_bad_token_raises(self):
        verification_mock = MagicMock()
        verification_mock.verify.return_value = (False, {"reason": "Invalid token"})

        with patch.object(self.backend, "otp_model", MagicMock()) as mock_model:
            mock_model.DoesNotExist = ObjectDoesNotExist
            mock_model.objects.get.return_value = verification_mock

            with self.assertRaises(AuthenticationFailed) as ctx:
                self.backend.authenticate(
                    request=None,
                    request_id="abc123",
                    token="9999",
                )

            self.assertEqual("Invalid token", str(ctx.exception))

    def test_authenticate_with_nonexistent_request(self):
        mock_model = MagicMock()
        mock_model.objects.get.side_effect = ObjectDoesNotExist
        mock_model.DoesNotExist = ObjectDoesNotExist

        with patch.object(self.backend, "otp_model", mock_model):

            result = self.backend.authenticate(
                    request=None,
                    request_id="does-not-exist",
                    token="1234",
                )
            self.assertEqual(result, None)


class TestPhoneNumberOTPBackend(TestEmailOTPBackend):
    backend = auth_backends.PhoneNumberOTPBackend()

