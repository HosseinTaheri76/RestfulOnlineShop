import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from locations.models import Province, City


class Command(BaseCommand):
    help = "Import provinces and cities from local JSON file inside the app."

    def handle(self, *args, **options):
        # Path to the JSON file inside app/data/
        app_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        json_path = os.path.join(app_dir, "data", "provinces.json")

        if not os.path.exists(json_path):
            self.stdout.write(self.style.ERROR(f"JSON file not found: {json_path}"))
            return

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.stdout.write("Importing provinces and cities...")

        with transaction.atomic():
            for province_data in data:
                province_name = province_data["name"].strip()

                province, _ = Province.objects.get_or_create(
                    title=province_name,
                    defaults={"is_active": True}
                )

                for city_name in province_data["cities"]:
                    city_name = city_name.strip()

                    City.objects.get_or_create(
                        province=province,
                        title=city_name,
                        defaults={"is_active": True}
                    )

        self.stdout.write(self.style.SUCCESS("Import completed successfully!"))
