from decimal import Decimal

from ..models import DailyResult
from .calculations import (
    calculate_actual_sales,
    calculate_expected_revenue,
    calculate_expected_sales_volume,
    calculate_fuel_cost,
    calculate_gross_profit,
    calculate_net_profit,
    calculate_pump_volume,
    calculate_tank_movement,
    get_product_settings,
    get_reconciliation_settings,
    reconcile_financial_sales,
    reconcile_physical_volume,
)


def simulate_daily_entry(daily_entry):
    """
    Simulate all operational and financial calculations for a DailyEntry.

    This function reads the raw data and configuration from the database,
    runs the individual business calculations, and returns the simulated
    result.

    It does NOT save anything to DailyResult.
    """

    # ---------------------------------------------------------
    # 1. Get reconciliation settings
    # ---------------------------------------------------------

    reconciliation_settings = get_reconciliation_settings(
        daily_entry.station,
        daily_entry.entry_date,
    )

    if reconciliation_settings is None:
        raise ValueError(
            "No reconciliation settings found for this date."
        )

    # ---------------------------------------------------------
    # 2. Calculate total pump volume
    # ---------------------------------------------------------

    pump_volume = Decimal("0")

    pump_readings = daily_entry.pump_readings.select_related("pump")

    for reading in pump_readings:
        pump_volume += calculate_pump_volume(reading)

    # ---------------------------------------------------------
    # 3. Calculate total tank movement
    # ---------------------------------------------------------

    tank_movement = Decimal("0")

    tank_readings = daily_entry.tank_readings.select_related("tank")

    for reading in tank_readings:
        tank_movement += calculate_tank_movement(reading)

    # ---------------------------------------------------------
    # 4. Physical reconciliation
    # ---------------------------------------------------------

    physical_result = reconcile_physical_volume(
        pump_volume=pump_volume,
        tank_movement=tank_movement,
        tolerance=reconciliation_settings.physical_tolerance,
    )

    # ---------------------------------------------------------
    # 5. Calculate expected revenue and fuel cost
    #
    # We calculate these per product because PMS and AGO can
    # have different selling prices and landing costs.
    # ---------------------------------------------------------

    expected_revenue = Decimal("0")
    fuel_cost = Decimal("0")

    for product_type in ["PMS", "AGO"]:

        product_tank_movement = Decimal("0")

        for reading in tank_readings:
            if reading.tank.product_type == product_type:
                product_tank_movement += calculate_tank_movement(
                    reading
                )

        # No movement for this product means there is nothing
        # to calculate for this product.
        if product_tank_movement == Decimal("0"):
            continue

        product_settings = get_product_settings(
            daily_entry.station,
            product_type,
            daily_entry.entry_date,
        )

        if product_settings is None:
            raise ValueError(
                f"No product settings found for {product_type} "
                f"on {daily_entry.entry_date}."
            )

        expected_sales_volume = calculate_expected_sales_volume(
            tank_movement=product_tank_movement,
            adjustment_divisor=reconciliation_settings.adjustment_divisor,
            adjustment_factor=reconciliation_settings.adjustment_factor,
        )

        product_expected_revenue = calculate_expected_revenue(
            expected_sales_volume=expected_sales_volume,
            selling_price=product_settings.selling_price,
        )

        product_fuel_cost = calculate_fuel_cost(
            tank_movement=product_tank_movement,
            landing_cost=product_settings.landing_cost,
        )

        expected_revenue += product_expected_revenue
        fuel_cost += product_fuel_cost

    # ---------------------------------------------------------
    # 6. Calculate actual financial sales
    # ---------------------------------------------------------

    financial_transactions = list(
        daily_entry.financial_transactions.all()
    )

    actual_sales = calculate_actual_sales(
        financial_transactions
    )

    # ---------------------------------------------------------
    # 7. Financial reconciliation
    # ---------------------------------------------------------

    financial_result = reconcile_financial_sales(
        expected_revenue=expected_revenue,
        actual_sales=actual_sales,
    )

    # ---------------------------------------------------------
    # 8. Calculate expenses
    # ---------------------------------------------------------

    expenses = sum(
        (
            transaction.amount
            for transaction in financial_transactions
            if transaction.transaction_type == "expense"
        ),
        Decimal("0"),
    )

    # ---------------------------------------------------------
    # 9. Calculate profit
    # ---------------------------------------------------------

    gross_profit = calculate_gross_profit(
        expected_revenue=expected_revenue,
        fuel_cost=fuel_cost,
    )

    net_profit = calculate_net_profit(
        gross_profit=gross_profit,
        expenses=expenses,
    )

    # ---------------------------------------------------------
    # 10. Return simulation result
    # ---------------------------------------------------------

    return {
        "daily_entry": daily_entry,

        # Physical reconciliation
        "pump_volume": pump_volume,
        "tank_movement": tank_movement,
        "physical_difference": physical_result["difference"],
        "physical_within_tolerance": physical_result[
            "within_tolerance"
        ],

        # Financial reconciliation
        "expected_revenue": expected_revenue,
        "actual_sales": actual_sales,
        "financial_difference": financial_result["difference"],

        # Profit
        "fuel_cost": fuel_cost,
        "gross_profit": gross_profit,
        "expenses": expenses,
        "net_profit": net_profit,
    }


def save_daily_result(daily_entry, simulation):
    """
    Persist the result of a daily simulation.

    If a result already exists for the DailyEntry, update it.
    Otherwise, create a new DailyResult.
    """

    result, created = DailyResult.objects.update_or_create(
        daily_entry=daily_entry,
        defaults={
            "pump_volume": simulation["pump_volume"],
            "tank_movement": simulation["tank_movement"],
            "physical_difference": simulation["physical_difference"],
            "physical_within_tolerance": simulation["physical_within_tolerance"],
            "expected_revenue": simulation["expected_revenue"],
            "actual_sales": simulation["actual_sales"],
            "financial_difference": simulation["financial_difference"],
            "fuel_cost": simulation["fuel_cost"],
            "gross_profit": simulation["gross_profit"],
            "expenses": simulation["expenses"],
            "net_profit": simulation["net_profit"],
        },
    )

    return result