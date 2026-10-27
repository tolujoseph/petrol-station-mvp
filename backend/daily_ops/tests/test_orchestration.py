from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from daily_ops.models import (
    DailyEntry,
    DailyResult,
    FinancialTransaction,
    ProductSettings,
    Pump,
    PumpReading,
    ReconciliationSettings,
    Station,
    Tank,
    TankReading,
    User,
)
from daily_ops.services.orchestration import (
    save_daily_result,
    simulate_daily_entry,
)


class OrchestrationTests(TestCase):

    def setUp(self):
        self.station = Station.objects.create(
            name="Test Station",
            location="Leeds",
        )

        self.manager = User.objects.create_user(
            username="manager",
            password="password123",
            station=self.station,
            role=User.Role.MANAGER,
        )

        self.pump = Pump.objects.create(
            station=self.station,
            label="Pump 1",
            product_type=Pump.ProductType.PMS,
        )

        self.tank = Tank.objects.create(
            station=self.station,
            label="Tank 1",
            product_type=Tank.ProductType.PMS,
        )

        self.product_settings = ProductSettings.objects.create(
            station=self.station,
            product_type=ProductSettings.ProductType.PMS,
            selling_price=Decimal("1.50"),
            landing_cost=Decimal("1.00"),
            effective_from=date(2026, 10, 1),
        )

        self.reconciliation_settings = (
            ReconciliationSettings.objects.create(
                station=self.station,
                adjustment_divisor=Decimal("20"),
                adjustment_factor=Decimal("0.85"),
                physical_tolerance=Decimal("5"),
                effective_from=date(2026, 10, 1),
            )
        )

    def test_simulate_daily_entry(self):
        """
        Test that orchestration correctly combines the individual
        calculations into one daily simulation.
        """

        # Previous day's pump and tank readings
        previous_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 1),
            status=DailyEntry.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )

        PumpReading.objects.create(
            daily_entry=previous_entry,
            pump=self.pump,
            closing_reading=Decimal("1000"),
        )

        TankReading.objects.create(
            daily_entry=previous_entry,
            tank=self.tank,
            closing_reading=Decimal("5000"),
        )

        # Today's entry
        daily_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 2),
        )

        PumpReading.objects.create(
            daily_entry=daily_entry,
            pump=self.pump,
            closing_reading=Decimal("1100"),
        )

        TankReading.objects.create(
            daily_entry=daily_entry,
            tank=self.tank,
            closing_reading=Decimal("4900"),
        )

        # Actual financial sales
        FinancialTransaction.objects.create(
            daily_entry=daily_entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=FinancialTransaction.TransactionType.POS,
            amount=Decimal("150"),
        )

        FinancialTransaction.objects.create(
            daily_entry=daily_entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=(
                FinancialTransaction.TransactionType.CASH_BANK
            ),
            amount=Decimal("10"),
        )

        simulation = simulate_daily_entry(daily_entry)

        # Pump volume: 1100 - 1000 = 100 litres
        self.assertEqual(simulation["pump_volume"], Decimal("100"))

        # Tank movement: 5000 - 4900 = 100 litres
        self.assertEqual(simulation["tank_movement"], Decimal("100"))

        # Litres the dips account for: 100 + (100 / 20 * 0.85) = 104.25,
        # so the pumps are 4.25 litres off, inside the 5 litre tolerance.
        self.assertEqual(simulation["physical_difference"], Decimal("4.25"))
        self.assertTrue(simulation["physical_within_tolerance"])

        # Sales value comes from the pumps: 100 litres x 1.50 = 150
        self.assertEqual(simulation["expected_revenue"], Decimal("150"))

        # Money recorded: 150 + 10 = 160, so 10 more than the pumps sold
        self.assertEqual(simulation["actual_sales"], Decimal("160"))
        self.assertEqual(simulation["financial_difference"], Decimal("-10"))
        self.assertTrue(simulation["financial_within_tolerance"])

        # Fuel cost: tank litres x landing cost = 100 x 1.00
        self.assertEqual(simulation["fuel_cost"], Decimal("100"))

        # Gross profit: 150 - 100 = 50; no expenses
        self.assertEqual(simulation["gross_profit"], Decimal("50"))
        self.assertEqual(simulation["expenses"], Decimal("0"))
        self.assertEqual(simulation["net_profit"], Decimal("50"))

        self.assertEqual([product["product_type"] for product in simulation["products"]], ["PMS"])

    def test_save_daily_result(self):
        """
        Test that a simulation can be persisted as a DailyResult.
        """

        previous_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 1),
            status=DailyEntry.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )

        PumpReading.objects.create(
            daily_entry=previous_entry,
            pump=self.pump,
            closing_reading=Decimal("1000"),
        )

        TankReading.objects.create(
            daily_entry=previous_entry,
            tank=self.tank,
            closing_reading=Decimal("5000"),
        )

        daily_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 2),
        )

        PumpReading.objects.create(
            daily_entry=daily_entry,
            pump=self.pump,
            closing_reading=Decimal("1100"),
        )

        TankReading.objects.create(
            daily_entry=daily_entry,
            tank=self.tank,
            closing_reading=Decimal("4900"),
        )

        FinancialTransaction.objects.create(
            daily_entry=daily_entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=FinancialTransaction.TransactionType.POS,
            amount=Decimal("150"),
        )

        simulation = simulate_daily_entry(daily_entry)

        result = save_daily_result(
            daily_entry,
            simulation,
        )

        self.assertEqual(
            result.daily_entry,
            daily_entry,
        )

        self.assertEqual(
            result.pump_volume,
            Decimal("100"),
        )

        self.assertEqual(
            result.tank_movement,
            Decimal("100"),
        )

        self.assertEqual(
            result.physical_difference,
            Decimal("4.25"),
        )

        self.assertEqual(
            result.expected_revenue,
            Decimal("150"),
        )

        self.assertEqual(
            result.fuel_cost,
            Decimal("100"),
        )

        self.assertEqual(
            result.gross_profit,
            Decimal("50"),
        )

        self.assertEqual(
            result.net_profit,
            Decimal("50"),
        )

    def test_save_daily_result_updates_existing_result(self):
        """
        Test that re-running a simulation updates the existing
        DailyResult instead of creating a duplicate.
        """

        previous_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 1),
            status=DailyEntry.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )

        PumpReading.objects.create(
            daily_entry=previous_entry,
            pump=self.pump,
            closing_reading=Decimal("1000"),
        )

        TankReading.objects.create(
            daily_entry=previous_entry,
            tank=self.tank,
            closing_reading=Decimal("5000"),
        )

        daily_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 2),
        )

        pump_reading = PumpReading.objects.create(
            daily_entry=daily_entry,
            pump=self.pump,
            closing_reading=Decimal("1100"),
        )

        TankReading.objects.create(
            daily_entry=daily_entry,
            tank=self.tank,
            closing_reading=Decimal("4900"),
        )

        FinancialTransaction.objects.create(
            daily_entry=daily_entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=FinancialTransaction.TransactionType.POS,
            amount=Decimal("150"),
        )

        # First simulation
        simulation = simulate_daily_entry(daily_entry)

        first_result = save_daily_result(
            daily_entry,
            simulation,
        )

        # Change the raw pump reading
        pump_reading.closing_reading = Decimal("1120")
        pump_reading.save()

        # Run simulation again
        simulation = simulate_daily_entry(daily_entry)

        second_result = save_daily_result(
            daily_entry,
            simulation,
        )

        # The same DailyResult should have been updated
        self.assertEqual(
            first_result.id,
            second_result.id,
        )

        # New pump volume:
        # 1120 - 1000 = 120
        self.assertEqual(
            second_result.pump_volume,
            Decimal("120"),
        )

        # There should still only be one result
        self.assertEqual(
            DailyResult.objects.filter(
                daily_entry=daily_entry
            ).count(),
            1,
        )

    def test_products_reconcile_separately(self):
        """A PMS shortage must not be hidden by an AGO surplus on the same day."""
        ago_pump = Pump.objects.create(station=self.station, label="AGO Pump", product_type=Pump.ProductType.AGO)
        ago_tank = Tank.objects.create(station=self.station, label="AGO Tank", product_type=Tank.ProductType.AGO)
        ProductSettings.objects.create(
            station=self.station,
            product_type=ProductSettings.ProductType.AGO,
            selling_price=Decimal("2.00"),
            landing_cost=Decimal("1.50"),
            effective_from=date(2026, 10, 1),
        )
        previous_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 1),
            status=DailyEntry.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )
        for pump, value in [(self.pump, "1000"), (ago_pump, "500")]:
            PumpReading.objects.create(daily_entry=previous_entry, pump=pump, closing_reading=Decimal(value))
        for tank, value in [(self.tank, "5000"), (ago_tank, "3000")]:
            TankReading.objects.create(daily_entry=previous_entry, tank=tank, closing_reading=Decimal(value))

        daily_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 2),
        )
        for pump, value in [(self.pump, "1100"), (ago_pump, "550")]:
            PumpReading.objects.create(daily_entry=daily_entry, pump=pump, closing_reading=Decimal(value))
        for tank, value in [(self.tank, "4904.08"), (ago_tank, "2952.04")]:
            TankReading.objects.create(daily_entry=daily_entry, tank=tank, closing_reading=Decimal(value))
        # PMS sold 150 but only 140 was recorded; AGO sold 100 but 110 was recorded.
        for product, amount in [("PMS", "140"), ("AGO", "110")]:
            FinancialTransaction.objects.create(
                daily_entry=daily_entry,
                product_type=product,
                transaction_type=FinancialTransaction.TransactionType.POS,
                amount=Decimal(amount),
            )
        self.reconciliation_settings.financial_tolerance = Decimal("5")
        self.reconciliation_settings.save()

        simulation = simulate_daily_entry(daily_entry)
        products = {product["product_type"]: product for product in simulation["products"]}

        self.assertEqual(simulation["financial_difference"], Decimal("0"))
        self.assertEqual(products["PMS"]["financial_difference"], Decimal("10"))
        self.assertEqual(products["AGO"]["financial_difference"], Decimal("-10"))
        self.assertFalse(simulation["financial_within_tolerance"])
        self.assertTrue(simulation["physical_within_tolerance"])

        result = save_daily_result(daily_entry, simulation)
        result.refresh_from_db()
        self.assertEqual(
            [(row["product_type"], row["financial_difference"]) for row in result.product_results],
            [("PMS", "10.00"), ("AGO", "-10.00")],
        )
        self.assertFalse(result.financial_within_tolerance)

