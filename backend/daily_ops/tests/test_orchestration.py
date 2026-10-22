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

        # Pump volume:
        # 1100 - 1000 = 100
        self.assertEqual(
            simulation["pump_volume"],
            Decimal("100"),
        )

        # Tank movement:
        # 5000 - 4900 = 100
        self.assertEqual(
            simulation["tank_movement"],
            Decimal("100"),
        )

        # Physical difference:
        # 100 - 100 = 0
        self.assertEqual(
            simulation["physical_difference"],
            Decimal("0"),
        )

        self.assertTrue(
            simulation["physical_within_tolerance"]
        )

        # Expected sales volume:
        #
        # 100 + (100 / 20 * 0.85)
        # = 104.25
        #
        # Expected revenue:
        #
        # 104.25 * 1.50
        # = 156.375
        #
        # Decimal arithmetic is used, so we expect this exact value.
        self.assertEqual(
            simulation["expected_revenue"],
            Decimal("156.375"),
        )

        # Actual sales:
        # 150 + 10 = 160
        self.assertEqual(
            simulation["actual_sales"],
            Decimal("160"),
        )

        # Financial difference:
        # 156.375 - 160 = -3.625
        self.assertEqual(
            simulation["financial_difference"],
            Decimal("-3.625"),
        )

        # Fuel cost:
        # 100 * 1.00 = 100
        self.assertEqual(
            simulation["fuel_cost"],
            Decimal("100"),
        )

        # Gross profit:
        # 156.375 - 100 = 56.375
        self.assertEqual(
            simulation["gross_profit"],
            Decimal("56.375"),
        )

        # No expenses in this test
        self.assertEqual(
            simulation["expenses"],
            Decimal("0"),
        )

        # Net profit:
        # 56.375 - 0 = 56.375
        self.assertEqual(
            simulation["net_profit"],
            Decimal("56.375"),
        )

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
            Decimal("0"),
        )

        self.assertEqual(
            result.expected_revenue,
            Decimal("156.375"),
        )

        self.assertEqual(
            result.fuel_cost,
            Decimal("100"),
        )

        self.assertEqual(
            result.gross_profit,
            Decimal("56.375"),
        )

        self.assertEqual(
            result.net_profit,
            Decimal("56.375"),
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