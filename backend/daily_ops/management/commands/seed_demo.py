"""Create local demo data so the frontend works on a fresh database.

Safe to re-run: existing records are reused and demo passwords are reset.
For local development only.
"""

import os
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import Client

from daily_ops.models import (
    DailyEntry,
    DailyResult,
    FuelDelivery,
    Pump,
    ProductSettings,
    ReconciliationSettings,
    Station,
    Tank,
    User,
)

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
    help = "Seed a demo station, pumps, tanks, settings, login users and recent history for local development."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14, help="Days of submitted history to create (0 to skip).")

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

        self.seed_settings(station)
        if options["days"] > 0:
            self.seed_history(station, options["days"])

        self.stdout.write(self.style.SUCCESS(f"Demo data ready for '{station.name}'."))
        self.stdout.write(f"Logins (password: {DEMO_PASSWORD}): manager, owner, admin (Django admin access)")

    def seed_settings(self, station):
        start = date.today() - timedelta(days=365)
        for product, price, cost in [("PMS", "617.00", "560.00"), ("AGO", "1100.00", "1020.00")]:
            ProductSettings.objects.get_or_create(
                station=station, product_type=product, effective_from=start,
                defaults={"selling_price": Decimal(price), "landing_cost": Decimal(cost)},
            )
        ReconciliationSettings.objects.get_or_create(station=station, effective_from=start)

    @transaction.atomic
    def seed_history(self, station, days):
        """Submit past daily entries through the real API so results are genuinely reconciled."""
        if DailyResult.objects.filter(daily_entry__station=station).exists():
            self.stdout.write("History already present, skipping.")
            return

        rng = random.Random(42)
        client = Client()
        client.force_login(User.objects.get(username="manager"))
        host = {"HTTP_HOST": "localhost"}
        pumps = list(Pump.objects.filter(station=station, active=True))
        tanks = list(Tank.objects.filter(station=station, active=True))
        pump_totals = {p.id: Decimal(150000 + 40000 * i) for i, p in enumerate(pumps)}
        tank_levels = {t.id: Decimal(34000) for t in tanks}
        price = {"PMS": Decimal("617.00"), "AGO": Decimal("1100.00")}

        def submit(entry_date, pump_readings, tank_readings, sales):
            transactions = []
            if sales:
                transactions = [
                    {"product_type": "PMS", "transaction_type": "POS", "amount": f"{sales * Decimal('0.6'):.2f}", "description": "POS settlement"},
                    {"product_type": "PMS", "transaction_type": "cash_bank", "amount": f"{sales * Decimal('0.4'):.2f}", "description": "Cash banked"},
                    {"transaction_type": "expense", "amount": "12500.00", "description": "Generator diesel"},
                ]
            payload = {
                "entry_date": entry_date.isoformat(),
                "notes": "",
                "pump_readings": [{"pump": k, "closing_reading": f"{v:.2f}"} for k, v in pump_readings.items()],
                "tank_readings": [{"tank": k, "closing_reading": f"{v:.2f}"} for k, v in tank_readings.items()],
                "financial_transactions": transactions,
            }
            created = client.post("/api/daily-entries/", payload, content_type="application/json", **host)
            if created.status_code != 201:
                raise RuntimeError(f"Could not create demo entry for {entry_date}: {created.content.decode()}")
            entry_id = created.json()["id"]
            done = client.post(f"/api/daily-entries/{entry_id}/finalise/", **host)
            if done.status_code != 200:
                raise RuntimeError(f"Could not finalise demo entry for {entry_date}: {done.content.decode()}")
            return DailyResult.objects.get(daily_entry_id=entry_id)

        # Day zero establishes the baseline readings.
        start = date.today() - timedelta(days=days + 1)
        submit(start, pump_totals, tank_levels, None)

        for offset in range(days):
            entry_date = start + timedelta(days=offset + 1)
            volumes = {p.id: Decimal(rng.randint(900, 1900)) for p in pumps}
            for p in pumps:
                pump_totals[p.id] += volumes[p.id]
            for t in tanks:
                drawn = sum(volumes[p.id] for p in pumps if p.product_type == t.product_type)
                restock = Decimal(0)
                if tank_levels[t.id] - drawn < 8000:  # keep tanks topped up
                    restock = Decimal(30000)
                    FuelDelivery.objects.create(tank=t, delivery_date=entry_date, quantity=restock)
                tank_levels[t.id] = tank_levels[t.id] - drawn + restock
            variance_day = offset % 5 == 3
            # First pass learns the expected revenue; the second becomes the official entry.
            probe = submit(entry_date, pump_totals, tank_levels, None)
            sales = probe.expected_revenue * (Decimal("0.97") if variance_day else Decimal(1))
            submit(entry_date, pump_totals, tank_levels, sales.quantize(Decimal("0.01")))

        self.stdout.write(f"Created {days} days of submitted history.")
