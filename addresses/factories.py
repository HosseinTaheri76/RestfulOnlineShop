import factory
from factory import Faker

from accounts.factories import UserFactory
from locations.factories import CityFactory

from .models import UserAddress


class UserAddressFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = UserAddress

    # -----------------------
    # Relations
    # -----------------------
    user = factory.SubFactory(UserFactory)
    city = factory.SubFactory(CityFactory)

    @factory.lazy_attribute
    def province(self):
        # Ensures city always belongs to province
        return self.city.province

    # -----------------------
    # Basic Fields
    # -----------------------
    # Unique per user because (user, title) is unique_together
    title = factory.Sequence(lambda n: f"Address #{n}")

    street = Faker("street_name")
    address_line_2 = Faker("secondary_address")

    building_number = factory.Sequence(lambda n: (n % 90) + 1)
    unit_number = factory.Sequence(lambda n: (n % 10) + 1)

    # Valid 10-digit Iranian postal code
    postal_code = Faker("bothify", text="##########")   # 10 digits

    # -----------------------
    # Recipient Info
    # (auto-filled if missing)
    # -----------------------
    recipient_full_name = ""
    recipient_phone = ""

    is_default = False

    # Ensure recipient_* are auto-filled in clean() if blank
