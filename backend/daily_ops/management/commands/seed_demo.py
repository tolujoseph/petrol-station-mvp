"""Set up the Omesh station with its logins, prices and a couple of days of history.

Safe to re-run: existing records are reused and the login passwords are reset.
`--reset` first wipes every station, record and the old demo logins.
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
    PumpReadingEvidence,
    ReconciliationSettings,
    Station,
    Tank,
    TankReadingEvidence,
    User,
)

DEMO_STATION = "Omesh"
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "omesh")

# Mirrors the station's spreadsheet: four petrol pumps, one diesel pump, two petrol pits and a diesel pit.
PUMPS = [("Pump 1", "PMS", "251613.93"), ("Pump 2", "PMS", "734049.99"), ("Pump 3", "PMS", "468141.93"), ("Pump 4", "PMS", "731284.90"), ("Pump 5", "AGO", "500459.63")]
TANKS = [("Pit 1", "PMS", "6000"), ("Pit 2", "PMS", "13500"), ("Pit 3", "AGO", "9000")]
# Selling price and landing cost per litre, from late May in the spreadsheet.
PRICES = {"PMS": ("880.00", "840.50"), "AGO": ("990.00", "971.00")}
USERS = [
    # username, role, is_admin (may delete records and use the Django admin)
    ("omesh-admin", User.Role.OWNER, True),
    ("omesh-owner", User.Role.OWNER, False),
    ("omesh-manager", User.Role.MANAGER, False),
]
# Logins from earlier versions of this command, removed by --reset.
OLD_USERNAMES = ["manager", "owner", "admin"]


class Command(BaseCommand):
    help = "Seed a demo station, pumps, tanks, settings, login users and recent history for local development."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=2, help="Days of submitted history to create (0 to skip).")
        parser.add_argument("--reset", action="store_true", help="Wipe all stations, records, settings and old demo logins first.")

    def handle(self, *args, **options):
        if options["reset"]:
            self.reset()
        station, _ = Station.objects.get_or_create(name=DEMO_STATION)
        # Only lay out equipment on a new station, so re-running never adds pumps to an existing one.
        if not station.pumps.exists():
            for label, product, _ in PUMPS:
                Pump.objects.create(station=station, label=label, product_type=product)
            for label, product, _ in TANKS:
                Tank.objects.create(station=station, label=label, product_type=product)

        for username, role, superuser in USERS:
            user, _ = User.objects.get_or_create(username=username)
            user.station = station
            user.role = role
            user.is_staff = superuser
            user.is_superuser = superuser
            user.set_password(DEMO_PASSWORD)
            user.save()

        self.seed_settings(station)
        if options["days"] > 0:
            self.seed_history(station, options["days"])

        self.stdout.write(self.style.SUCCESS(f"Demo data ready for '{station.name}'."))
        self.stdout.write(f"Logins (password: {DEMO_PASSWORD}): omesh-manager, omesh-owner, omesh-admin (can delete records)")

    @transaction.atomic
    def reset(self):
        for evidence in [*PumpReadingEvidence.objects.all(), *TankReadingEvidence.objects.all()]:
            evidence.image.delete(save=False)
        # Entries first: readings protect the pumps and tanks they belong to.
        DailyEntry.objects.all().delete()
        for model in (FuelDelivery, ProductSettings, ReconciliationSettings, Pump, Tank):
            model.objects.all().delete()
        User.objects.filter(username__in=OLD_USERNAMES).delete()
        Station.objects.all().delete()
        self.stdout.write("Wiped all stations, records and settings.")

    def seed_settings(self, station):
        start = date.today() - timedelta(days=365)
        for product, (price, cost) in PRICES.items():
            ProductSettings.objects.get_or_create(
                station=station, product_type=product, effective_from=start,
                defaults={"selling_price": Decimal(price), "landing_cost": Decimal(cost)},
            )
        # In the spreadsheet, pump and adjusted tank litres usually differ by up to ~100 L a day.
        ReconciliationSettings.objects.get_or_create(
            station=station, effective_from=start,
            defaults={"physical_tolerance": Decimal("120"), "financial_tolerance": Decimal("1000")},
        )

    @transaction.atomic
    def seed_history(self, station, days):
        """Submit past daily entries through the real API so results are genuinely reconciled."""
        if DailyEntry.objects.filter(station=station).exists():
            self.stdout.write("History already present, skipping.")
            return

        rng = random.Random(42)
        client = Client()
        client.force_login(User.objects.get(username="omesh-manager"))
        host = {"HTTP_HOST": "localhost"}
        pumps = list(Pump.objects.filter(station=station, active=True).order_by("id"))
        tanks = list(Tank.objects.filter(station=station, active=True).order_by("id"))
        meters = {p.id: Decimal(start) for p, (_, _, start) in zip(pumps, PUMPS)}
        levels = {t.id: Decimal(start) for t, (_, _, start) in zip(tanks, TANKS)}
        price = {product: Decimal(selling) for product, (selling, _) in PRICES.items()}
        adjustment = Decimal("1") + Decimal("0.85") / Decimal("20")
        cent = Decimal("0.01")

        def submit(entry_date, deliveries, transactions, opening=False):
            payload = {
                "entry_date": entry_date.isoformat(),
                "notes": "",
                "pump_readings": [{"pump": k, "closing_reading": f"{v:.2f}"} for k, v in meters.items()],
                "tank_readings": [
                    {"tank": k, "closing_reading": f"{v:.2f}", "delivered_quantity": f"{deliveries.get(k, 0):.2f}"}
                    for k, v in levels.items()
                ],
                "financial_transactions": transactions,
            }
            created = client.post("/api/daily-entries/", payload, content_type="application/json", **host)
            if created.status_code != 201:
                raise RuntimeError(f"Could not create demo entry for {entry_date}: {created.content.decode()}")
            entry_id = created.json()["id"]
            done = client.post(f"/api/daily-entries/{entry_id}/finalise/", **host)
            if done.status_code != 200:
                raise RuntimeError(f"Could not finalise demo entry for {entry_date}: {done.content.decode()}")
            if opening:
                # Opening readings are only the baseline for the first day, not a trading day of their own.
                DailyResult.objects.filter(daily_entry_id=entry_id).delete()

        def money(product, amount):
            """Split a fuel's takings across POS, cash/bank and an occasional expense, like the spreadsheet."""
            pos = (amount * Decimal("0.72")).quantize(Decimal("1"))
            expense = Decimal(rng.choice([0, 0, 15000, 25000])) if product == "PMS" else Decimal(0)
            rows = [
                {"product_type": product, "transaction_type": "POS", "amount": f"{pos:.2f}", "description": "POS settlement"},
                {"product_type": product, "transaction_type": "cash_bank", "amount": f"{amount - pos - expense:.2f}", "description": "Cash banked"},
            ]
            if expense:
                rows.append({"product_type": product, "transaction_type": "expense", "amount": f"{expense:.2f}", "description": "Generator diesel"})
            return rows

        # Opening readings the day before the history starts.
        start = date.today() - timedelta(days=days + 1)
        submit(start, {}, [], opening=True)

        for offset in range(days):
            entry_date = start + timedelta(days=offset + 1)
            sold = {"PMS": Decimal(0), "AGO": Decimal(0)}
            for p in pumps:
                litres = Decimal(rng.randint(500, 950) if p.product_type == "PMS" else rng.randint(150, 900)) + Decimal(rng.randint(0, 99)) / 100
                meters[p.id] += litres
                sold[p.product_type] += litres

            deliveries = {}
            for product in sold:
                # Tank dips account for pump litres once the spreadsheet adjustment is applied, give or take a little.
                used = (sold[product] / adjustment + rng.randint(-40, 40)).quantize(cent)
                product_tanks = [t for t in tanks if t.product_type == product]
                for t in product_tanks:
                    share = (used / len(product_tanks)).quantize(cent)
                    if levels[t.id] - share < 2000:
                        deliveries[t.id] = Decimal(15000 if product == "PMS" else 10000)
                    levels[t.id] += deliveries.get(t.id, 0) - share

            takings = {product: (sold[product] * price[product]).quantize(Decimal("1")) for product in sold}
            if offset % 7 == 3:
                takings["PMS"] -= Decimal(25000)  # a short day
            transactions = money("PMS", takings["PMS"]) + money("AGO", takings["AGO"])
            if offset % 9 == 5:
                # A transfer for petrol recorded under diesel: PMS short, AGO over by the same amount.
                transactions[0]["amount"] = f"{Decimal(transactions[0]['amount']) - 300000:.2f}"
                transactions.append({"product_type": "AGO", "transaction_type": "transfer", "amount": "300000.00", "description": "Customer transfer"})
            submit(entry_date, deliveries, transactions)

        self.stdout.write(f"Created {days} days of submitted history.")
