from datetime import timedelta
from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, NotFound

from otp.models import OTPGrant, EmailOTP
from otp.permissions import OTPGrantRequired
from django.contrib.auth import get_user_model

from freezegun import freeze_time

User = get_user_model()


class DummyView(APIView):
    permission_classes = [OTPGrantRequired]
    purpose = "login"


class TestOTPGrantRequired(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="u1", email="u1@example.com", password="pass"
        )
        self.otp = EmailOTP.objects.create(user=self.user)
        self.permission = OTPGrantRequired()
        self.view = DummyView()
        self.grant = OTPGrant.objects.create(
            user=self.user,
            purpose="login",
            expires_at=timezone.now() + timedelta(minutes=5),
        )

    def test_valid_permission_allows_access_and_sets_view_attr(self):
        request = self.factory.get("/")
        self.view.kwargs = {"grant_id": str(self.grant.id)}

        result = self.permission.has_permission(request, self.view)

        self.assertTrue(result)
        self.assertTrue(hasattr(self.view, "grant"))
        self.assertEqual(self.view.grant, self.grant)

    def test_invalid_purpose_raises_permission_denied(self):
        self.grant.purpose = "register"
        self.grant.save()

        request = self.factory.get("/")
        self.view.kwargs = {"grant_id": str(self.grant.id)}

        with self.assertRaises(PermissionDenied):
            self.permission.has_permission(request, self.view)

    def test_expired_grant_raises_permission_denied(self):
        with freeze_time(timezone.now() + timedelta(hours=1)):
            request = self.factory.get("/")
            self.view.kwargs = {"grant_id": str(self.grant.id)}

            with self.assertRaises(PermissionDenied):
                self.permission.has_permission(request, self.view)

    def test_missing_grant_raises_not_found(self):
        request = self.factory.get("/")
        self.view.kwargs = {"grant_id": "00000000-0000-0000-0000-000000000000"}

        with self.assertRaises(NotFound):
            self.permission.has_permission(request, self.view)

    def test_missing_purpose_asserts(self):
        class NoPurposeView(DummyView):
            purpose = None

        view = NoPurposeView()
        request = self.factory.get("/")
        view.kwargs = {"grant_id": str(self.grant.id)}

        with self.assertRaises(AssertionError):
            self.permission.has_permission(request, view)

    def test_missing_perm_id_asserts(self):
        request = self.factory.get("/")
        self.view.kwargs = {}

        with self.assertRaises(AssertionError):
            self.permission.has_permission(request, self.view)
