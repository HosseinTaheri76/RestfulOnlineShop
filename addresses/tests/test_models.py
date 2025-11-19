from django.test import TestCase
from django.core.exceptions import ValidationError

from accounts.factories import UserFactory
from locations.factories import CityFactory, ProvinceFactory
from addresses.factories import UserAddressFactory


class TestUserAddressModel(TestCase):

    # --------------------------------------------------------------------
    # VALIDATION: recipient_full_name / phone derived from user
    # --------------------------------------------------------------------

    def test_missing_recipient_fullname_and_user_has_no_name_raises(self):
        user = UserFactory(first_name="", last_name="", phone_number_verified=True)
        address = UserAddressFactory.build(
            user=user,
            recipient_full_name="",  # must derive but cannot
        )
        with self.assertRaises(ValidationError) as ctx:
            address.full_clean()
        self.assertIn("recipient_full_name", ctx.exception.message_dict)

    def test_missing_recipient_phone_and_user_has_no_phone_raises(self):
        user = UserFactory(phone_number=None)
        address = UserAddressFactory.build(
            user=user,
            recipient_phone="",  # must derive but cannot
        )
        with self.assertRaises(ValidationError) as ctx:
            address.full_clean()
        self.assertIn("recipient_phone", ctx.exception.message_dict)

    def test_recipient_fields_auto_filled_when_user_has_data(self):
        user = UserFactory(
            first_name="ali",
            last_name="jimi",
            phone_number="+989121111111",
            phone_number_verified=True,
        )
        address = UserAddressFactory.build(
            user=user,
            recipient_full_name="",
            recipient_phone="",
            city=CityFactory(),
        )
        # should not raise
        address.full_clean()
        self.assertEqual(address.recipient_full_name, user.get_full_name())
        self.assertEqual(address.recipient_phone, user.get_usable_phone_number())

    # --------------------------------------------------------------------
    # VALIDATION: province/city relationship
    # --------------------------------------------------------------------

    def test_city_not_in_province_raises_error(self):
        province1 = ProvinceFactory()
        province2 = ProvinceFactory()

        city_wrong = CityFactory(province=province2)

        address = UserAddressFactory.build(
            province=province1,
            city=city_wrong,
        )

        with self.assertRaises(ValidationError) as ctx:
            address.full_clean()
        self.assertIn("city", ctx.exception.message_dict)

    # --------------------------------------------------------------------
    # VALIDATION: postal code
    # --------------------------------------------------------------------

    def test_postal_code_must_be_exactly_10_digits(self):
        address = UserAddressFactory.build(postal_code="12345")
        with self.assertRaises(ValidationError) as ctx:
            address.full_clean()
        self.assertIn("postal_code", ctx.exception.message_dict)

        address = UserAddressFactory.build(postal_code="abcdefghij")
        with self.assertRaises(ValidationError):
            address.full_clean()

    # --------------------------------------------------------------------
    # UNIQUE TOGETHER constraints
    # --------------------------------------------------------------------

    def test_unique_title_per_user(self):
        user = UserFactory(phone_number_verified=True)
        UserAddressFactory(user=user, title="Home")

        addr2 = UserAddressFactory.build(user=user, title="Home")

        with self.assertRaises(ValidationError) as ctx:
            addr2.save()

        self.assertIn("Title", str(ctx.exception.message_dict))

    def test_unique_postal_code_per_user(self):
        user = UserFactory(phone_number_verified=True)
        UserAddressFactory(user=user, postal_code="1234567890")

        addr2 = UserAddressFactory.build(user=user, postal_code="1234567890")

        with self.assertRaises(ValidationError) as ctx:
            addr2.save()

        self.assertIn("Postal code", str(ctx.exception.message_dict))

    # --------------------------------------------------------------------
    # DEFAULT ADDRESS LOGIC
    # --------------------------------------------------------------------

    def test_first_address_is_auto_default(self):
        user = UserFactory(phone_number_verified=True)
        addr = UserAddressFactory(user=user, is_default=False)
        addr.save()

        self.assertTrue(addr.is_default)

    def test_only_one_default_is_allowed(self):
        user = UserFactory(phone_number_verified=True)

        addr1 = UserAddressFactory(user=user, is_default=True)
        addr2 = UserAddressFactory(user=user, is_default=True)

        addr1.save()
        addr2.save()

        addr1.refresh_from_db()
        addr2.refresh_from_db()

        # addr2 becomes default, older defaults become non-default
        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)

    def test_updating_default_to_another_makes_old_default_false(self):
        user = UserFactory(phone_number_verified=True)

        addr1 = UserAddressFactory(user=user, is_default=True)
        addr2 = UserAddressFactory(user=user, is_default=False)

        addr1.save()
        addr2.save()

        # Make addr2 the new default
        addr2.is_default = True
        addr2.save()

        addr1.refresh_from_db()
        addr2.refresh_from_db()

        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)

    def test_user_change_not_allowed_for_default_address(self):
        user1 = UserFactory(phone_number_verified=True)
        user2 = UserFactory(phone_number_verified=True)
        addr = UserAddressFactory(user=user1, is_default=True)
        addr.save()

        addr.user = user2

        with self.assertRaises(ValidationError) as ctx:
            addr.full_clean()

        self.assertIn("user", ctx.exception.message_dict)

    def test_if_no_default_exists_new_address_becomes_default(self):
        user = UserFactory(phone_number_verified=True)

        addr1 = UserAddressFactory(user=user, is_default=False)
        addr1.save()

        addr2 = UserAddressFactory(user=user, is_default=False)
        addr2.save()

        addr1.refresh_from_db()
        addr2.refresh_from_db()

        # first address auto-default
        self.assertTrue(addr1.is_default)
        # second stays false
        self.assertFalse(addr2.is_default)

    # --------------------------------------------------------------------
    # MISC LOGIC
    # --------------------------------------------------------------------

    def test_str_representation(self):
        user = UserFactory(username="hossein", phone_number_verified=True)
        addr = UserAddressFactory(user=user, title="Work")
        self.assertEqual(str(addr), "hossein – Work")
