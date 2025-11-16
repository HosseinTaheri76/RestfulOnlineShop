from uuid import uuid4

from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework import exceptions

from accounts import serializers

User = get_user_model()


class TestUserCreateSerializer(TestCase):
    serializer_class = serializers.UserCreateSerializer

    def setUp(self):
        self.valid_password = "StrongPass123!"
        self.email = "test@example.com"
        self.phone = "+989123456789"
        self.data = {
            "email_or_phone_number": self.phone,
            "password1": self.valid_password,
            "password2": self.valid_password,
        }

    def get_serializer(self, email_or_phone):
        data = self.data.copy()
        data['email_or_phone_number'] = email_or_phone
        return self.serializer_class(data=data)

    def test_create_user_with_email(self):
        s = self.get_serializer(self.email)
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        self.assertEqual(user.email, self.email)
        self.assertTrue(user.check_password(self.valid_password))

    def test_create_user_with_phone(self):
        s = self.get_serializer(self.phone)
        self.assertTrue(s.is_valid(), s.errors)
        user = s.save()
        self.assertEqual(user.phone_number.as_e164, self.phone)
        self.assertTrue(user.check_password(self.valid_password))

    def test_reject_duplicate_email(self):
        User.objects.create_user(username=self.email, email=self.email, password="123Strong")
        s = self.get_serializer(self.email)
        self.assertFalse(s.is_valid())
        self.assertIn("email_or_phone_number", s.errors)

    def test_reject_duplicate_phone(self):
        User.objects.create_user(username=self.phone, phone_number=self.phone, password="123Strong")
        s = self.get_serializer(self.phone)
        self.assertFalse(s.is_valid())
        self.assertIn("email_or_phone_number", s.errors)

    def test_password_mismatch(self):
        self.data["password2"] = 'abc'
        s = self.get_serializer(self.email)
        self.assertFalse(s.is_valid())
        self.assertIn("password2", s.errors)

    def test_invalid_email_or_phone(self):
        s = self.get_serializer('abcd')
        self.assertFalse(s.is_valid())
        self.assertIn("email_or_phone_number", s.errors)


class TestPasswordLoginSerializer(TestCase):
    serializer_class = serializers.PasswordLoginSerializer

    def setUp(self):
        self.email = 'rtx5090@nvidia.com'
        self.phone = '+989121160188'
        self.password = 'geforce'
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            phone_number=self.phone,
            password=self.password
        )

    def test_login_success(self):
        serializer = self.serializer_class(data={'email_or_phone_number': self.email, 'password': self.password})
        self.assertTrue(serializer.is_valid())
        self.assertIn('access', serializer.data)
        self.assertIn('refresh', serializer.data)

    def test_login_failure(self):
        serializer = self.serializer_class(data={'email': self.email, 'password': '123'})
        self.assertFalse(serializer.is_valid())

    def test_invalid_email_or_phone(self):
        serializer = self.serializer_class(data={'email_or_phone_number': 'abcd', 'password': self.password})
        self.assertFalse(serializer.is_valid())


class TestOTPLoginConfirmSerializer(TestCase):
    serializer_class = serializers.OTPLoginConfirmSerializer

    def setUp(self):
        self.email = 'rtx5090@nvidia.com'
        self.phone = '+989121160188'
        self.password = 'geforce'
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            phone_number=self.phone,
            password=self.password
        )

    @patch('accounts.serializers.authenticate')
    def test_login_success(self, mocked_authenticate):
        mocked_authenticate.return_value = self.user
        serializer = self.serializer_class(data={'request_id': uuid4().hex, 'token': '123'})
        self.assertTrue(serializer.is_valid())
        self.assertIn('access', serializer.data)
        self.assertIn('refresh', serializer.data)

    @patch('accounts.serializers.authenticate')
    def test_login_failure_authentication_failed(self, mocked_authenticate):
        mocked_authenticate.side_effect = exceptions.AuthenticationFailed
        with self.assertRaises(exceptions.AuthenticationFailed):
            serializer = self.serializer_class(data={'request_id': uuid4().hex, 'token': '123'})
            serializer.is_valid()

    @patch('accounts.serializers.authenticate')
    def test_login_failure_authenticate_returns_none(self, mocked_authenticate):
        mocked_authenticate.return_value = None
        serializer = self.serializer_class(data={'request_id': uuid4().hex, 'token': '123'})
        self.assertFalse(serializer.is_valid())


class TestRequestEmailChangeSerializer(TestCase):
    serializer_class = serializers.RequestEmailChangeSerializer

    def setUp(self):
        request = MagicMock()
        self.user = User.objects.create_user(
            username='rtx5090',
            email='test@test.com',
        )
        request.user = self.user
        self.request = request
        self.new_email = 'newEmail@test.com'

    def test_duplicate_email(self):
        serializer = self.serializer_class(data={'email': self.user.email}, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('A user with this email already exists.', str(serializer.errors))

    @patch('otp.services.OTPService.request_otp')
    def test_serializer_calls_request_otp(self, mocked_request_otp):
        serializer = self.serializer_class(data={'email': self.new_email}, context={'request': self.request})
        serializer.is_valid()
        mocked_request_otp.assert_called_once()

    def test_valid_serializer(self):
        serializer = self.serializer_class(data={'email': self.new_email}, context={'request': self.request})
        serializer.is_valid()
        self.assertIn('request_id', serializer.data)
        self.assertIn('expires_at', serializer.data)


class TestRequestPhoneChangeSerializer(TestCase):
    serializer_class = serializers.RequestPhoneChangeSerializer

    def setUp(self):
        request = MagicMock()
        self.user = User.objects.create_user(
            username='rtx5090',
            phone_number='+989123350189',
        )
        request.user = self.user
        self.request = request
        self.new_phone = '+989123810288'

    def test_duplicate_phone(self):
        serializer = self.serializer_class(data={'phone': self.user.phone_number}, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('A user with this phone number already exists.', str(serializer.errors))

    @patch('otp.services.OTPService.request_otp')
    def test_serializer_calls_request_otp(self, mocked_request_otp):
        serializer = self.serializer_class(data={'phone': self.new_phone}, context={'request': self.request})
        serializer.is_valid()
        mocked_request_otp.assert_called_once()

    def test_valid_serializer(self):
        serializer = self.serializer_class(data={'phone': self.new_phone}, context={'request': self.request})
        serializer.is_valid()
        self.assertIn('request_id', serializer.data)
        self.assertIn('expires_at', serializer.data)


class PasswordResetSerializerTests(TestCase):
    serializer_class = serializers.PasswordResetSerializer

    def setUp(self):
        self.user = User.objects.create_user(
            username="u1@example.com",
            email="u1@example.com",
            password="StrongPass123!"
        )
        self.valid_data = {"password1": "NewStrongPass123!", "password2": "NewStrongPass123!"}

    def test_valid_password_reset(self):
        s = self.serializer_class(data=self.valid_data)
        self.assertTrue(s.is_valid(), s.errors)
        s.update(self.user, s.validated_data)
        self.assertTrue(self.user.check_password("NewStrongPass123!"))

    def test_password_mismatch(self):
        s = self.serializer_class(data={"password1": "NewStrongPass123!", "password2": "NewStrongPass123!22"})
        self.assertFalse(s.is_valid())
        self.assertIn("non_field_errors", s.errors)


class PasswordChangeSerializerTests(TestCase):
    serializer_class = serializers.PasswordChangeSerializer

    def setUp(self):
        self.user = User.objects.create_user(
            username="a@example.com",
            email="a@example.com",
            password="OldPass123!"
        )

    def test_valid_password_change(self):
        data = {"old_password": "OldPass123!", "new_password1": "NewPass123!", "new_password2": "NewPass123!"}
        s = self.serializer_class(instance=self.user, data=data)
        self.assertTrue(s.is_valid(), s.errors)
        s.update(self.user, s.validated_data)
        self.assertTrue(self.user.check_password("NewPass123!"))

    def test_wrong_old_password(self):
        data = {"old_password": "WrongOld!", "new_password1": "NewPass123!", "new_password2": "NewPass123!"}
        s = self.serializer_class(instance=self.user, data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("old_password", s.errors)

    def test_mismatch_new_passwords(self):
        data = {"old_password": "OldPass123!", "new_password1": "NewPass123ww!", "new_password2": "NewPass123!"}
        s = self.serializer_class(instance=self.user, data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("non_field_errors", s.errors)
