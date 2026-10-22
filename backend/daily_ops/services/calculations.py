
from decimal import Decimal

from daily_ops.models import (
    FinancialTransaction,
    FuelDelivery,
    ProductSettings,
    PumpReading,
    ReconciliationSettings,
    TankReading,
)
from .querysets import official_daily_entry_ids


def calculate_pump_volume(reading: PumpReading) -> Decimal:
    official_ids = official_daily_entry_ids(reading.daily_entry.station)
    previous_reading = (
        PumpReading.objects.filter(
            pump=reading.pump,
            daily_entry_id__in=official_ids,
            daily_entry__entry_date__lt=reading.daily_entry.entry_date,
        )
        .order_by(
            "-daily_entry__entry_date",
            "-daily_entry__submitted_at",
            "-daily_entry_id",
        )
        .first()
    )

    if previous_reading is None:
        return Decimal("0.00")

    return reading.closing_reading - previous_reading.closing_reading


def calculate_tank_movement(reading: TankReading) -> Decimal:
    official_ids = official_daily_entry_ids(reading.daily_entry.station)
    previous_reading = (
        TankReading.objects.filter(
            tank=reading.tank,
            daily_entry_id__in=official_ids,
            daily_entry__entry_date__lt=reading.daily_entry.entry_date,
        )
        .order_by(
            "-daily_entry__entry_date",
            "-daily_entry__submitted_at",
            "-daily_entry_id",
        )
        .first()
    )

    if previous_reading is None:
        return Decimal("0.00")

    opening_stock = previous_reading.closing_reading

    deliveries = FuelDelivery.objects.filter(
        tank=reading.tank,
        delivery_date=reading.daily_entry.entry_date,
    )

    total_deliveries = sum(
        (delivery.quantity for delivery in deliveries),
        Decimal("0.00"),
    )

    return opening_stock + total_deliveries - reading.closing_reading


def reconcile_physical_volume(
    pump_volume: Decimal,
    tank_movement: Decimal,
    tolerance: Decimal,
) -> dict:
    difference = abs(pump_volume - tank_movement)

    return {
        "pump_volume": pump_volume,
        "tank_movement": tank_movement,
        "difference": difference,
        "within_tolerance": difference <= tolerance,
    }


def calculate_expected_sales_volume(
    tank_movement: Decimal,
    adjustment_divisor: Decimal,
    adjustment_factor: Decimal,
) -> Decimal:
    if adjustment_divisor == 0:
        raise ValueError("Adjustment divisor cannot be zero.")

    adjustment = (
        tank_movement / adjustment_divisor
    ) * adjustment_factor

    return tank_movement + adjustment


def calculate_expected_revenue(
    expected_sales_volume: Decimal,
    selling_price: Decimal,
) -> Decimal:
    return expected_sales_volume * selling_price


def get_product_settings(
    station,
    product_type,
    entry_date,
) -> ProductSettings | None:
    return (
        ProductSettings.objects.filter(
            station=station,
            product_type=product_type,
            effective_from__lte=entry_date,
        )
        .order_by("-effective_from")
        .first()
    )


def get_reconciliation_settings(
    station,
    entry_date,
) -> ReconciliationSettings | None:
    return (
        ReconciliationSettings.objects.filter(
            station=station,
            effective_from__lte=entry_date,
        )
        .order_by("-effective_from")
        .first()
    )


def calculate_actual_sales(transactions) -> Decimal:
    sales_transaction_types = {
        FinancialTransaction.TransactionType.POS,
        FinancialTransaction.TransactionType.CASH_BANK,
        FinancialTransaction.TransactionType.CREDIT,
    }

    return sum(
        (
            item.amount
            for item in transactions
            if item.transaction_type in sales_transaction_types
        ),
        Decimal("0.00"),
    )


def reconcile_financial_sales(
    expected_revenue: Decimal,
    actual_sales: Decimal,
) -> dict:
    difference = expected_revenue - actual_sales

    return {
        "expected_revenue": expected_revenue,
        "actual_sales": actual_sales,
        "difference": difference,
    }


def calculate_fuel_cost(
    tank_movement: Decimal,
    landing_cost: Decimal,
) -> Decimal:
    return tank_movement * landing_cost


def calculate_gross_profit(
    expected_revenue: Decimal,
    fuel_cost: Decimal,
) -> Decimal:
    return expected_revenue - fuel_cost


def calculate_net_profit(
    gross_profit: Decimal,
    expenses: Decimal,
) -> Decimal:
    return gross_profit - expenses
