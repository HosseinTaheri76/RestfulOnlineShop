import random

import factory
from factory import Faker
from factory.django import DjangoModelFactory

from phonenumber_field.phonenumber import PhoneNumber

from accounts.models import User


class UserFactory(DjangoModelFactory):
    """Factory for the custom User model."""

    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    first_name = Faker("first_name")
    last_name = Faker("last_name")

    # Generate unique email for tests
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    email_verified = False

    # Generate unique Iranian phone number
    phone_number = factory.LazyAttribute(
        lambda _: PhoneNumber.from_string(f"+98912{random.randint(1000000, 9999999)}")
    )
    phone_number_verified = False

    # Ensure a usable password is set
    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        """
        Allow tests to override the password:
            UserFactory(password="mypassword")
        """
        pwd = extracted or "testpassword123"
        self.set_password(pwd)
        if create:
            self.save()
