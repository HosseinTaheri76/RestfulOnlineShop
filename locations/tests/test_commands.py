import json
from unittest.mock import patch, mock_open

from django.core.management import call_command
from django.test import TestCase

from locations.models import Province, City


VALID_JSON = json.dumps([
    {"name": "Province A", "cities": ["City 1", "City 2"]},
    {"name": "Province B", "cities": ["City X"]},
])

INVALID_JSON = "{ invalid json ]"


class LoadLocationsCommandTests(TestCase):

    @patch("locations.management.commands.load_locations.open",
           new_callable=mock_open,
           read_data=VALID_JSON)
    @patch("os.path.exists", return_value=True)
    def test_import_creates_provinces_and_cities(self, mock_exists, mock_file):
        call_command("load_locations")

        self.assertEqual(Province.objects.count(), 2)
        self.assertEqual(City.objects.count(), 3)

    @patch("locations.management.commands.load_locations.open",
           new_callable=mock_open,
           read_data=VALID_JSON)
    @patch("os.path.exists", return_value=True)
    def test_idempotent_import(self, mock_exists, mock_file):
        call_command("load_locations")
        call_command("load_locations")

        self.assertEqual(Province.objects.count(), 2)
        self.assertEqual(City.objects.count(), 3)

    @patch("os.path.exists", return_value=False)
    def test_missing_file_creates_nothing(self, mock_exists):
        call_command("load_locations")

        self.assertEqual(Province.objects.count(), 0)
        self.assertEqual(City.objects.count(), 0)

    @patch("locations.management.commands.load_locations.open",
           new_callable=mock_open,
           read_data=INVALID_JSON)
    @patch("os.path.exists", return_value=True)
    def test_invalid_json_rolls_back(self, mock_file, mock_exists):
        with self.assertRaises(Exception):
            call_command("load_locations")

        self.assertEqual(Province.objects.count(), 0)
        self.assertEqual(City.objects.count(), 0)
