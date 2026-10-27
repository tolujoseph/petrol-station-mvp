
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

    return (
        opening_stock
        + total_deliveries
        + reading.delivered_quantity
        - reading.closing_reading
    )


def reconcile_physical_volume(
    pump_volume: Decimal,
    expected_volume: Decimal,
    tolerance: Decimal,
) -> dict:
    """Compare litres sold at the pumps with the litres the tank dips account for."""
    difference = abs(pump_volume - expected_volume)

    return {
        "pump_volume": pump_volume,
        "expected_volume": expected_volume,
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


def calculate_sales_value(
    pump_volume: Decimal,
    selling_price: Decimal,
) -> Decimal:
    """Money the pumps say should have come in: litres sold x selling price."""
    return pump_volume * selling_price


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


def calculate_money_accounted(transactions) -> Decimal:
    """
    All money recorded against the day's sales.

    As in the station's spreadsheet, every line counts: POS, cash/bank,
    credit, transfers, shell deposits, and expenses paid out of the takings.
    """
    return sum((item.amount for item in transactions), Decimal("0.00"))


def calculate_expenses(transactions) -> Decimal:
    return sum(
        (
            item.amount
            for item in transactions
            if item.transaction_type == FinancialTransaction.TransactionType.EXPENSE
        ),
        Decimal("0.00"),
    )


def reconcile_financial_sales(
    sales_value: Decimal,
    money_accounted: Decimal,
    tolerance: Decimal,
) -> dict:
    """Positive difference means money is short of what the pumps sold."""
    difference = sales_value - money_accounted

    return {
        "sales_value": sales_value,
        "money_accounted": money_accounted,
        "difference": difference,
        "within_tolerance": abs(difference) <= tolerance,
    }


def calculate_fuel_cost(
    tank_movement: Decimal,
    landing_cost: Decimal,
) -> Decimal:
    return tank_movement * landing_cost


def calculate_gross_profit(
    sales_value: Decimal,
    fuel_cost: Decimal,
) -> Decimal:
    return sales_value - fuel_cost


def calculate_net_profit(
    gross_profit: Decimal,
    expenses: Decimal,
) -> Decimal:
    return gross_profit - expenses
