
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from daily_ops.models import (
    DailyEntry,
    FinancialTransaction,
    FuelDelivery,
    ProductSettings,
    Pump,
    PumpReading,
    ReconciliationSettings,
    Station,
    Tank,
    TankReading,
    User,
)
from daily_ops.services.calculations import (
    calculate_expected_sales_volume,
    calculate_expenses,
    calculate_fuel_cost,
    calculate_gross_profit,
    calculate_money_accounted,
    calculate_net_profit,
    calculate_pump_volume,
    calculate_sales_value,
    calculate_tank_movement,
    get_product_settings,
    get_reconciliation_settings,
    reconcile_financial_sales,
    reconcile_physical_volume,
)


class CalculationTests(TestCase):
    def setUp(self):
        self.station = Station.objects.create(
            name="Test Station",
            location="Leeds",
        )
        self.manager = User.objects.create_user(
            username="testmanager",
            password="testpassword",
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

    def test_calculates_pump_volume_from_previous_closing_reading(self):
        previous_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 4),
            status=DailyEntry.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )
        PumpReading.objects.create(
            daily_entry=previous_entry,
            pump=self.pump,
            closing_reading=Decimal("52430.50"),
        )

        current_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 5),
        )
        current_reading = PumpReading.objects.create(
            daily_entry=current_entry,
            pump=self.pump,
            closing_reading=Decimal("52680.50"),
        )

        result = calculate_pump_volume(current_reading)

        self.assertEqual(result, Decimal("250.00"))

    def test_returns_zero_when_no_previous_pump_reading_exists(self):
        entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 5),
        )
        reading = PumpReading.objects.create(
            daily_entry=entry,
            pump=self.pump,
            closing_reading=Decimal("52680.50"),
        )

        result = calculate_pump_volume(reading)

        self.assertEqual(result, Decimal("0"))

    def test_draft_pump_reading_is_not_used_as_previous_baseline(self):
        draft_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 4),
            status=DailyEntry.Status.DRAFT,
        )
        PumpReading.objects.create(
            daily_entry=draft_entry,
            pump=self.pump,
            closing_reading=Decimal("52430.50"),
        )
        current_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 5),
        )
        current_reading = PumpReading.objects.create(
            daily_entry=current_entry,
            pump=self.pump,
            closing_reading=Decimal("52680.50"),
        )

        self.assertEqual(calculate_pump_volume(current_reading), Decimal("0.00"))

    def test_calculates_tank_movement_with_delivery(self):
        previous_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 4),
            status=DailyEntry.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )
        TankReading.objects.create(
            daily_entry=previous_entry,
            tank=self.tank,
            closing_reading=Decimal("20000.00"),
        )

        current_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 5),
        )
        FuelDelivery.objects.create(
            tank=self.tank,
            delivery_date=date(2026, 10, 5),
            quantity=Decimal("10000.00"),
        )
        current_reading = TankReading.objects.create(
            daily_entry=current_entry,
            tank=self.tank,
            closing_reading=Decimal("25000.00"),
        )

        result = calculate_tank_movement(current_reading)

        self.assertEqual(result, Decimal("5000.00"))

    def test_tank_movement_includes_delivery_entered_with_dip(self):
        previous_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 4),
            status=DailyEntry.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )
        TankReading.objects.create(daily_entry=previous_entry, tank=self.tank, closing_reading=Decimal("3350.00"))
        current_entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 5),
        )
        reading = TankReading.objects.create(
            daily_entry=current_entry,
            tank=self.tank,
            closing_reading=Decimal("13100.00"),
            delivered_quantity=Decimal("10000.00"),
        )

        # 3350 + 10000 delivered - 13100 left = 250 litres sold
        self.assertEqual(calculate_tank_movement(reading), Decimal("250.00"))

    def test_physical_reconciliation_is_within_tolerance(self):
        result = reconcile_physical_volume(
            pump_volume=Decimal("5000.00"),
            expected_volume=Decimal("4970.00"),
            tolerance=Decimal("50.00"),
        )

        self.assertEqual(result["difference"], Decimal("30.00"))
        self.assertTrue(result["within_tolerance"])

    def test_physical_reconciliation_exceeds_tolerance(self):
        result = reconcile_physical_volume(
            pump_volume=Decimal("5000.00"),
            expected_volume=Decimal("4900.00"),
            tolerance=Decimal("50.00"),
        )

        self.assertEqual(result["difference"], Decimal("100.00"))
        self.assertFalse(result["within_tolerance"])

    def test_calculates_expected_sales_volume(self):
        result = calculate_expected_sales_volume(
            tank_movement=Decimal("10000.00"),
            adjustment_divisor=Decimal("20.00"),
            adjustment_factor=Decimal("0.85"),
        )

        self.assertEqual(result, Decimal("10425.00"))

    def test_sales_value_uses_pump_litres(self):
        result = calculate_sales_value(
            pump_volume=Decimal("2414.30"),
            selling_price=Decimal("890.00"),
        )

        self.assertEqual(result, Decimal("2148727.00"))

    def test_gets_latest_product_settings_for_entry_date(self):
        ProductSettings.objects.create(
            station=self.station,
            product_type=ProductSettings.ProductType.PMS,
            selling_price=Decimal("1.50"),
            landing_cost=Decimal("1.20"),
            effective_from=date(2026, 10, 1),
        )
        ProductSettings.objects.create(
            station=self.station,
            product_type=ProductSettings.ProductType.PMS,
            selling_price=Decimal("1.55"),
            landing_cost=Decimal("1.25"),
            effective_from=date(2026, 10, 8),
        )

        settings = get_product_settings(
            station=self.station,
            product_type=ProductSettings.ProductType.PMS,
            entry_date=date(2026, 10, 5),
        )

        self.assertIsNotNone(settings)
        self.assertEqual(settings.selling_price, Decimal("1.50"))

    def test_gets_latest_reconciliation_settings_for_entry_date(self):
        ReconciliationSettings.objects.create(
            station=self.station,
            adjustment_divisor=Decimal("20.00"),
            adjustment_factor=Decimal("0.85"),
            physical_tolerance=Decimal("50.00"),
            effective_from=date(2026, 10, 1),
        )
        ReconciliationSettings.objects.create(
            station=self.station,
            adjustment_divisor=Decimal("25.00"),
            adjustment_factor=Decimal("0.90"),
            physical_tolerance=Decimal("75.00"),
            effective_from=date(2026, 10, 8),
        )

        settings = get_reconciliation_settings(
            station=self.station,
            entry_date=date(2026, 10, 5),
        )

        self.assertIsNotNone(settings)
        self.assertEqual(settings.physical_tolerance, Decimal("50.00"))

    def test_money_accounted_counts_every_transaction_type(self):
        entry = DailyEntry.objects.create(
            station=self.station,
            manager=self.manager,
            entry_date=date(2026, 10, 5),
        )

        FinancialTransaction.objects.create(
            daily_entry=entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=FinancialTransaction.TransactionType.POS,
            amount=Decimal("10000.00"),
        )
        FinancialTransaction.objects.create(
            daily_entry=entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=FinancialTransaction.TransactionType.CASH_BANK,
            amount=Decimal("4000.00"),
        )
        FinancialTransaction.objects.create(
            daily_entry=entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=FinancialTransaction.TransactionType.CREDIT,
            amount=Decimal("1500.00"),
        )
        FinancialTransaction.objects.create(
            daily_entry=entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=FinancialTransaction.TransactionType.EXPENSE,
            amount=Decimal("500.00"),
        )

        FinancialTransaction.objects.create(
            daily_entry=entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=FinancialTransaction.TransactionType.TRANSFER,
            amount=Decimal("2000.00"),
        )
        FinancialTransaction.objects.create(
            daily_entry=entry,
            product_type=FinancialTransaction.ProductType.PMS,
            transaction_type=FinancialTransaction.TransactionType.SHELL_DEPOSIT,
            amount=Decimal("300.00"),
        )

        transactions = entry.financial_transactions.all()

        # Like the station spreadsheet, every money line counts towards the day's
        # takings: POS + cash/bank + credit + expense + transfer + shell deposit.
        self.assertEqual(calculate_money_accounted(transactions), Decimal("18300.00"))
        self.assertEqual(calculate_expenses(transactions), Decimal("500.00"))

    def test_reconciles_financial_sales(self):
        result = reconcile_financial_sales(
            sales_value=Decimal("2148727.00"),
            money_accounted=Decimal("2149308.00"),
            tolerance=Decimal("1000.00"),
        )

        self.assertEqual(result["difference"], Decimal("-581.00"))
        self.assertTrue(result["within_tolerance"])

        short = reconcile_financial_sales(
            sales_value=Decimal("2891040.40"),
            money_accounted=Decimal("2445290.00"),
            tolerance=Decimal("1000.00"),
        )

        self.assertEqual(short["difference"], Decimal("445750.40"))
        self.assertFalse(short["within_tolerance"])

    def test_calculates_fuel_cost(self):
        result = calculate_fuel_cost(
            tank_movement=Decimal("10000.00"),
            landing_cost=Decimal("1.20"),
        )

        self.assertEqual(result, Decimal("12000.00"))

    def test_calculates_gross_profit(self):
        result = calculate_gross_profit(
            sales_value=Decimal("15637.50"),
            fuel_cost=Decimal("12000.00"),
        )

        self.assertEqual(result, Decimal("3637.50"))

    def test_calculates_net_profit(self):
        result = calculate_net_profit(
            gross_profit=Decimal("3637.50"),
            expenses=Decimal("1000.00"),
        )

        self.assertEqual(result, Decimal("2637.50"))
