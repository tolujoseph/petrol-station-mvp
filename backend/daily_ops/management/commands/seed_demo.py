"""Create local demo data so the frontend works on a fresh database.

Safe to re-run: existing records are reused and demo passwords are reset.
For local development only.
"""

import os

from django.core.management.base import BaseCommand

from daily_ops.models import Pump, Station, Tank, User

DEMO_STATION = "Javeln Ikeja Forecourt"
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo12345")

PUMPS = [("Pump 1", "PMS"), ("Pump 2", "PMS"), ("Pump 3", "AGO")]
TANKS = [("Tank A", "PMS"), ("Tank B", "AGO")]
USERS = [
    # username, role, is_superuser
    ("manager", User.Role.MANAGER, False),
    ("owner", User.Role.OWNER, False),
    ("admin", User.Role.MANAGER, True),
]


class Command(BaseCommand):
    help = "Seed a demo station, pumps, tanks and login users for local development."

    def handle(self, *args, **options):
        station, _ = Station.objects.get_or_create(
            name=DEMO_STATION, defaults={"location": "Ikeja, Lagos"}
        )
        for label, product in PUMPS:
            Pump.objects.get_or_create(station=station, label=label, defaults={"product_type": product})
        for label, product in TANKS:
            Tank.objects.get_or_create(station=station, label=label, defaults={"product_type": product})

        for username, role, superuser in USERS:
            user, _ = User.objects.get_or_create(username=username)
            user.station = station
            user.role = role
            user.is_staff = superuser or user.is_staff
            user.is_superuser = superuser or user.is_superuser
            user.set_password(DEMO_PASSWORD)
            user.save()

        self.stdout.write(self.style.SUCCESS(f"Demo data ready for '{station.name}'."))
        self.stdout.write(f"Logins (password: {DEMO_PASSWORD}): manager, owner, admin (Django admin access)")
