from django.urls import reverse
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from accounts.factories import UserFactory
from locations.factories import CityFactory, ProvinceFactory
from addresses.factories import UserAddressFactory   # your UserAddress factory
from addresses.models import UserAddress


class UserAddressViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory(phone_number_verified=True)
        self.client.force_authenticate(self.user)
        self.url_list = reverse("addresses:address-list")   # router name: <basename>-list

    # ----------------------------------------------
    # Helpers
    # ----------------------------------------------
    def create_payload(self, **overrides):
        city = overrides.pop("city", None) or CityFactory()
        return {
            "title": overrides.pop("title", "Home"),
            "recipient_full_name": overrides.pop("recipient_full_name", ""),
            "recipient_phone": overrides.pop("recipient_phone", ""),
            "province": city.province.id,
            "city": city.id,
            "street": overrides.pop("street", "Main street"),
            "address_line_2": overrides.pop("address_line_2", ""),
            "building_number": overrides.pop("building_number", 4),
            "unit_number": overrides.pop("unit_number", 2),
            "postal_code": overrides.pop("postal_code", "1234567890"),
            "is_default": overrides.pop("is_default", False),
            **overrides,
        }

    # ----------------------------------------------
    # BASIC ACCESS TESTS
    # ----------------------------------------------
    def test_user_can_list_their_own_addresses(self):
        UserAddressFactory(user=self.user)
        UserAddressFactory(user=UserFactory(phone_number_verified=True))  # belongs to another user

        response = self.client.get(self.url_list)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_user_can_retrieve_their_own_address(self):
        addr = UserAddressFactory(user=self.user)
        url = reverse("addresses:address-detail", args=[addr.id])

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_cannot_access_other_users_address(self):
        other_addr = UserAddressFactory(user=UserFactory(phone_number_verified=True))
        url = reverse("addresses:address-detail", args=[other_addr.id])

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ----------------------------------------------
    # CREATE TESTS + MODEL VALIDATION
    # ----------------------------------------------

    def test_create_address_success_default_filled_from_user(self):
        """recipient_full_name and recipient_phone empty → filled from user"""
        self.user.phone_number = "+989111111111"
        self.user.first_name = "Bob"
        self.user.last_name = "Stone"
        self.user.save()

        payload = self.create_payload(recipient_full_name="", recipient_phone="")
        response = self.client.post(self.url_list, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        addr = UserAddress.objects.get(id=response.data["id"])
        self.assertEqual(addr.recipient_full_name, "Bob Stone")
        self.assertEqual(str(addr.recipient_phone), "+989111111111")

    def test_create_fails_if_no_user_phone_and_no_recipient_phone(self):
        """Model clean() enforces this rule"""
        self.user.phone_number = None
        self.user.save()

        payload = self.create_payload(recipient_phone="")
        response = self.client.post(self.url_list, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("recipient_phone", response.data)

    def test_create_fails_if_no_user_fullname_and_no_recipient_fullname(self):
        self.user.first_name = ""
        self.user.last_name = ""
        self.user.save()

        payload = self.create_payload(recipient_full_name="")
        response = self.client.post(self.url_list, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("recipient_full_name", response.data)

    def test_postal_code_validation(self):
        payload = self.create_payload(postal_code="abcd")
        response = self.client.post(self.url_list, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("postal_code", response.data)

    def test_city_province_mismatch(self):
        city = CityFactory()
        wrong_province = ProvinceFactory()

        payload = self.create_payload(
            city=city,
            province=wrong_province.id,
        )
        payload["province"] = wrong_province.id

        response = self.client.post(self.url_list, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("city", response.data)

    # ----------------------------------------------
    # UNIQUE TOGETHER VALIDATION
    # ----------------------------------------------
    def test_unique_title_per_user(self):
        UserAddressFactory(user=self.user, title="Home")

        payload = self.create_payload(title="Home")

        response = self.client.post(self.url_list, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Title", str(response.data))

    def test_unique_postal_code_per_user(self):
        UserAddressFactory(user=self.user, postal_code="1111111111")

        payload = self.create_payload(postal_code="1111111111")

        response = self.client.post(self.url_list, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Postal code", str(response.data))

    # ----------------------------------------------
    # DEFAULT ADDRESS LOGIC
    # ----------------------------------------------

    def test_first_address_auto_becomes_default_if_none_exists(self):
        payload = self.create_payload(is_default=False)
        response = self.client.post(self.url_list, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        addr = UserAddress.objects.get(id=response.data["id"])
        self.assertTrue(addr.is_default)

    def test_set_one_address_as_default_disables_other(self):
        a1 = UserAddressFactory(user=self.user, is_default=True)
        a2 = UserAddressFactory(user=self.user, is_default=False)

        url = reverse("addresses:address-detail", args=[a2.id])
        response = self.client.patch(url, {"is_default": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        a1.refresh_from_db()
        a2.refresh_from_db()
        self.assertFalse(a1.is_default)
        self.assertTrue(a2.is_default)

    # ----------------------------------------------
    # UPDATE TESTS
    # ----------------------------------------------

    def test_update_address_city_province_mismatch(self):
        addr = UserAddressFactory(user=self.user)
        wrong_province = ProvinceFactory()

        url = reverse("addresses:address-detail", args=[addr.id])

        response = self.client.patch(url, {"province": wrong_province.id}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("city", response.data)

    # ----------------------------------------------
    # DELETE TESTS
    # ----------------------------------------------
    def test_user_can_delete_their_own_address(self):
        addr = UserAddressFactory(user=self.user)
        url = reverse("addresses:address-detail", args=[addr.id])

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_user_cannot_delete_others_address(self):
        addr = UserAddressFactory(user=UserFactory(phone_number_verified=True))
        url = reverse("addresses:address-detail", args=[addr.id])

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
