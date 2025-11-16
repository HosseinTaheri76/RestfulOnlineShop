from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APITestCase

from otp.models import OTPGrant

User = get_user_model()


class UserCreateViewTests(APITestCase):
    def test_signup_creates_user(self):
        url = reverse("accounts:create")
        data = {
            "email_or_phone_number": "test@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="test@example.com").exists())


class PasswordLoginViewTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="a@example.com",
            email="a@example.com",
            password="OldPass123!"
        )

    def test_successful_login(self):
        url = reverse("accounts:password-login")
        data = {'email_or_phone_number': self.user.email, 'password': 'OldPass123!'}
        response = self.client.post(url, data)
        self.assertIn('access', response.json())


class ChangePasswordViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="a@example.com", email="a@example.com", password="OldPass123!")

    def test_change_password_success(self):
        self.client.force_authenticate(self.user)
        url = reverse("accounts:change-password")
        data = {
            "old_password": "OldPass123!",
            "new_password1": "NewPass456!",
            "new_password2": "NewPass456!",
        }
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass456!"))

    def test_unauthorized_user_fail(self):
        url = reverse("accounts:change-password")
        data = {
            "old_password": "OldPass123!",
            "new_password1": "NewPass456!",
            "new_password2": "NewPass456!",
        }
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetFlowTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="geforcertx5090@nvidia.com",
            email="geforcertx5090@nvidia.com",
            password="oldpassword123",
        )
        self.new_password = "abc123aabb"

    @patch("otp.models.EmailOTP.verify")
    def get_grant_for_password_reset(self, mocked_verify):
        """
        Returns a valid OTPGrant for password reset.
        """
        mocked_verify.return_value = (True, {})
        email = self.user.email

        request_id = self.client.post(
            reverse("accounts:password-reset-request", kwargs={"channel": "email"}),
            data={"email": email},
        ).json()["request_id"]

        return self.client.post(
            reverse("accounts:password-reset-confirm", kwargs={"channel": "email"}),
            data={"request_id": request_id, "token": "abcd"},
        ).json()["grant_id"]

    # -----------------------------------------------------
    # 1. SUCCESSFUL PASSWORD RESET
    # -----------------------------------------------------
    def test_password_reset_success(self):
        grant_id = self.get_grant_for_password_reset()

        response = self.client.post(
            reverse("accounts:password-reset-complete", kwargs={"grant_id": grant_id}),
            data={"password1": self.new_password, "password2": self.new_password},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))

        grant = OTPGrant.objects.get(pk=grant_id)
        self.assertFalse(grant.is_usable())

    # -----------------------------------------------------
    # 2. GRANT CANNOT BE REUSED
    # -----------------------------------------------------
    def test_password_reset_grant_cannot_be_reused(self):
        grant_id = self.get_grant_for_password_reset()

        # First usage → OK
        self.client.post(
            reverse("accounts:password-reset-complete", kwargs={"grant_id": grant_id}),
            data={"password1": self.new_password, "password2": self.new_password},
        )

        # Second usage → Forbidden
        response = self.client.post(
            reverse("accounts:password-reset-complete", kwargs={"grant_id": grant_id}),
            data={"password1": "zzzzzz123", "password2": "zzzzzz123"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -----------------------------------------------------
    # 3. GRANT EXPIRED
    # -----------------------------------------------------
    def test_password_reset_with_expired_grant(self):
        grant_id = self.get_grant_for_password_reset()
        grant = OTPGrant.objects.get(pk=grant_id)

        # Manually expire the grant
        grant.expires_at = timezone.now() - timedelta(seconds=10)
        grant.save()

        response = self.client.post(
            reverse("accounts:password-reset-complete", kwargs={"grant_id": grant_id}),
            data={"password1": self.new_password, "password2": self.new_password},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -----------------------------------------------------
    # 4. GRANT DOES NOT EXIST
    # -----------------------------------------------------
    def test_password_reset_with_invalid_grant(self):
        response = self.client.post(
            reverse("accounts:password-reset-complete",
                    kwargs={"grant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}),
            data={"password1": self.new_password, "password2": self.new_password},
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # -----------------------------------------------------
    # 5. PASSWORD MISMATCH VALIDATION
    # -----------------------------------------------------
    def test_password_reset_password_mismatch(self):
        grant_id = self.get_grant_for_password_reset()

        response = self.client.post(
            reverse("accounts:password-reset-complete", kwargs={"grant_id": grant_id}),
            data={"password1": "abc123aabb", "password2": "different"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.json())

    # -----------------------------------------------------
    # 7. ATOMICITY CHECK
    # -----------------------------------------------------
    @patch("accounts.serializers.PasswordResetSerializer.save")
    def test_password_reset_atomicity(self, mocked_save):
        """
        If serializer.save() crashes, password must NOT change and grant must stay usable.
        """
        dummy_error = type('DummyError', (Exception,), {})
        mocked_save.side_effect = dummy_error

        grant_id = self.get_grant_for_password_reset()
        old_hash = self.user.password

        try:
            response = self.client.post(
                reverse("accounts:password-reset-complete", kwargs={"grant_id": grant_id}),
                data={"password1": self.new_password, "password2": self.new_password},
            )
        except dummy_error:
            response = Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # DRF should return 500
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

        # password unchanged
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, old_hash)

        # grant still usable
        grant = OTPGrant.objects.get(pk=grant_id)
        self.assertTrue(grant.is_usable())


class EmailVerificationFlowTests(APITestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='akbar',
            email="test@test.com",
            email_verified=False
        )

    def get_otp_request_id(self):
        return self.client.post(
            reverse("accounts:request-email-verification"),
            data={"email": self.user.email},
        ).json()['request_id']

    @patch('otp.models.EmailOTP.verify')
    def test_successful_email_verification(self, mocked_verify):
        mocked_verify.return_value = True, {}

        response = self.client.post(
            reverse('accounts:confirm-email-verification'),
            data={'request_id': self.get_otp_request_id(), 'token': '1234'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email_verified, True)


class PhoneVerificationFlowTests(APITestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='akbar',
            phone_number="+989302844580",
            phone_number_verified=False
        )

    def get_otp_request_id(self):
        return self.client.post(
            reverse("accounts:request-phone-verification"),
            data={"phone_number": self.user.phone_number},
        ).json()['request_id']

    @patch('otp.models.PhoneNumberOTP.verify')
    def test_successful_phone_verification(self, mocked_verify):
        mocked_verify.return_value = True, {}
        response = self.client.post(
            reverse('accounts:confirm-phone-verification'),
            data={'request_id': self.get_otp_request_id(), 'token': '1234'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number_verified, True)


class PhoneChangeFlowTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='akbar',
            phone_number="+989302844580",
        )
        self.new_phone = "+989123360799"

    def get_otp_request_id(self):
        return self.client.post(
            reverse("accounts:request-phone-change"),
            data={"phone": self.new_phone},
        ).json()['request_id']

    @patch('otp.models.PhoneNumberOTP.verify')
    def test_successful_phone_change(self, mocked_verify):
        mocked_verify.return_value = True, {}
        self.client.force_authenticate(self.user)
        response = self.client.post(
            reverse('accounts:confirm-phone-change'),
            data={'request_id': self.get_otp_request_id(), 'token': '1234'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, self.new_phone)
        self.assertEqual(self.user.phone_number_verified, True)


class EmailChangeFlowTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='akbar',
            email='rtx@geforce.com'
        )
        self.new_email = "gtx@geforce.com"

    def get_otp_request_id(self):
        return self.client.post(
            reverse("accounts:request-email-change"),
            data={"email": self.new_email},
        ).json()['request_id']

    @patch('otp.models.EmailOTP.verify')
    def test_successful_email_change(self, mocked_verify):
        mocked_verify.return_value = True, {}
        self.client.force_authenticate(self.user)
        response = self.client.post(
            reverse('accounts:confirm-email-change'),
            data={'request_id': self.get_otp_request_id(), 'token': '1234'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, self.new_email)
        self.assertEqual(self.user.email_verified, True)


class OTPLoginFlowTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='akbar',
            phone_number="+989302844580",
        )

    def get_otp_request_id(self):
        return self.client.post(
            reverse('accounts:request-otp-login', args=('phone',)),
            data={'phone_number': self.user.phone_number},
        ).json()['request_id']

    @patch('otp.models.PhoneNumberOTP.verify')
    def test_successful_otp_login(self, mocked_verify):
        mocked_verify.return_value = True, {}
        response = self.client.post(
            reverse('accounts:confirm-otp-login'),
            data={'request_id': self.get_otp_request_id(), 'token': '1234'},
        )
        self.assertIn('access', response.json())
        self.assertIn('refresh', response.json())
