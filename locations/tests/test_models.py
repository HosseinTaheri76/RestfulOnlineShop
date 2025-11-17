from django.test import TestCase
from django.utils import timezone

from locations.models import Province, City


class TestProvinceCityActivation(TestCase):

    # --------------------------------------------------------
    # Province → Cities
    # --------------------------------------------------------

    def test_province_deactivation_disables_all_cities(self):
        prov = Province.objects.create(title="X", is_active=True)
        c1 = City.objects.create(province=prov, title="A", is_active=True)
        c2 = City.objects.create(province=prov, title="B", is_active=True)

        prov.is_active = False
        prov.save()

        c1.refresh_from_db()
        c2.refresh_from_db()

        self.assertFalse(c1.is_active)
        self.assertFalse(c2.is_active)

    def test_province_activation_enables_all_cities(self):
        prov = Province.objects.create(title="X", is_active=False)
        c1 = City.objects.create(province=prov, title="A", is_active=False)
        c2 = City.objects.create(province=prov, title="B", is_active=False)

        prov.is_active = True
        prov.save()

        c1.refresh_from_db()
        c2.refresh_from_db()

        self.assertTrue(c1.is_active)
        self.assertTrue(c2.is_active)

    def test_province_save_does_nothing_when_is_active_unchanged(self):
        prov = Province.objects.create(title="X", is_active=True)
        c1 = City.objects.create(province=prov, title="A", is_active=False)

        prov.title = "Changed Title"
        prov.save()

        c1.refresh_from_db()
        # is_active should NOT be changed because province activation didn't change
        self.assertFalse(c1.is_active)

    # --------------------------------------------------------
    # City → Province
    # --------------------------------------------------------

    def test_city_activation_activates_province(self):
        prov = Province.objects.create(title="X", is_active=False)
        city = City.objects.create(province=prov, title="A", is_active=False)

        city.is_active = True
        city.save()

        prov.refresh_from_db()
        self.assertTrue(prov.is_active)

    def test_last_city_deactivation_disables_province(self):
        prov = Province.objects.create(title="X", is_active=True)
        c1 = City.objects.create(province=prov, title="A", is_active=True)
        c2 = City.objects.create(province=prov, title="B", is_active=False)

        c1.is_active = False
        c1.save()

        prov.refresh_from_db()
        self.assertFalse(prov.is_active)

    def test_city_deactivation_when_other_active_exists_does_not_disable_province(self):
        prov = Province.objects.create(title="X", is_active=True)
        active_city = City.objects.create(province=prov, title="A", is_active=True)
        inactive_city = City.objects.create(province=prov, title="B", is_active=True)

        # Deactivate one of them
        inactive_city.is_active = False
        inactive_city.save()

        prov.refresh_from_db()
        self.assertTrue(prov.is_active)

    def test_city_save_no_change_in_is_active_does_not_affect_province(self):
        prov = Province.objects.create(title="X", is_active=True)
        city = City.objects.create(province=prov, title="A", is_active=True)

        city.title = "Something Else"
        city.save()

        prov.refresh_from_db()

        self.assertTrue(prov.is_active)  # unchanged
