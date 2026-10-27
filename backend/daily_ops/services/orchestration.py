from decimal import Decimal

from ..models import DailyResult
from .calculations import (
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

PRODUCT_TYPES = ("PMS", "AGO")
CENT = Decimal("0.01")


def simulate_product(daily_entry, product_type, pump_readings, tank_readings, transactions, settings):
    """
    Reconcile one product the way the station's spreadsheet does.

    - Litres sold come from the pump meters.
    - The tank dips, adjusted by (movement / divisor) x factor, give the
      litres the pumps should show (physical check).
    - Pump litres x selling price is the money that should be in hand, and is
      compared with every money line recorded for the product (financial check).
    - Profit is that sales value minus tank litres x landing cost.

    Returns None when the product had no activity that day.
    """
    pump_volume = sum(
        (calculate_pump_volume(reading) for reading in pump_readings if reading.pump.product_type == product_type),
        Decimal("0"),
    )
    tank_movement = sum(
        (calculate_tank_movement(reading) for reading in tank_readings if reading.tank.product_type == product_type),
        Decimal("0"),
    )
    product_transactions = [item for item in transactions if item.product_type == product_type]

    if not pump_volume and not tank_movement and not product_transactions:
        return None

    product_settings = get_product_settings(daily_entry.station, product_type, daily_entry.entry_date)
    if product_settings is None:
        raise ValueError(f"No product settings found for {product_type} on {daily_entry.entry_date}.")

    expected_volume = calculate_expected_sales_volume(
        tank_movement=tank_movement,
        adjustment_divisor=settings.adjustment_divisor,
        adjustment_factor=settings.adjustment_factor,
    )
    physical = reconcile_physical_volume(pump_volume, expected_volume, settings.physical_tolerance)
    sales_value = calculate_sales_value(pump_volume, product_settings.selling_price)
    financial = reconcile_financial_sales(
        sales_value,
        calculate_money_accounted(product_transactions),
        settings.financial_tolerance,
    )
    fuel_cost = calculate_fuel_cost(tank_movement, product_settings.landing_cost)

    return {
        "product_type": product_type,
        "pump_volume": pump_volume,
        "tank_movement": tank_movement,
        "expected_volume": expected_volume,
        "physical_difference": physical["difference"],
        "physical_within_tolerance": physical["within_tolerance"],
        "selling_price": product_settings.selling_price,
        "sales_value": sales_value,
        "money_accounted": financial["money_accounted"],
        "financial_difference": financial["difference"],
        "financial_within_tolerance": financial["within_tolerance"],
        "fuel_cost": fuel_cost,
        "gross_profit": calculate_gross_profit(sales_value, fuel_cost),
        "expenses": calculate_expenses(product_transactions),
    }


def simulate_daily_entry(daily_entry):
    """
    Simulate all operational and financial calculations for a DailyEntry.

    Each product is reconciled on its own (see simulate_product) and the day's
    totals are the sum of the products. Money lines without a product (older
    entries) still count towards the day's totals.

    It does NOT save anything to DailyResult.
    """
    settings = get_reconciliation_settings(daily_entry.station, daily_entry.entry_date)
    if settings is None:
        raise ValueError("No reconciliation settings found for this date.")

    pump_readings = list(daily_entry.pump_readings.select_related("pump"))
    tank_readings = list(daily_entry.tank_readings.select_related("tank"))
    transactions = list(daily_entry.financial_transactions.all())

    products = [
        product
        for product_type in PRODUCT_TYPES
        if (product := simulate_product(daily_entry, product_type, pump_readings, tank_readings, transactions, settings))
    ]
    unassigned = [item for item in transactions if item.product_type not in PRODUCT_TYPES]

    def total(field):
        return sum((product[field] for product in products), Decimal("0"))

    expected_revenue = total("sales_value")
    actual_sales = total("money_accounted") + calculate_money_accounted(unassigned)
    fuel_cost = total("fuel_cost")
    expenses = total("expenses") + calculate_expenses(unassigned)
    gross_profit = calculate_gross_profit(expected_revenue, fuel_cost)

    return {
        "daily_entry": daily_entry,

        # Physical reconciliation (litres)
        "pump_volume": total("pump_volume"),
        "tank_movement": total("tank_movement"),
        "physical_difference": total("physical_difference"),
        "physical_within_tolerance": all(product["physical_within_tolerance"] for product in products),

        # Financial reconciliation: pump sales value against recorded money
        "expected_revenue": expected_revenue,
        "actual_sales": actual_sales,
        "financial_difference": expected_revenue - actual_sales,
        "financial_within_tolerance": (
            all(product["financial_within_tolerance"] for product in products)
            and abs(calculate_money_accounted(unassigned)) <= settings.financial_tolerance
        ),

        # Profit
        "fuel_cost": fuel_cost,
        "gross_profit": gross_profit,
        "expenses": expenses,
        "net_profit": calculate_net_profit(gross_profit, expenses),

        "products": products,
    }


def serialise_products(products):
    return [
        {
            key: value if isinstance(value, (bool, str)) else str(value.quantize(CENT))
            for key, value in product.items()
        }
        for product in products
    ]


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
            "financial_within_tolerance": simulation["financial_within_tolerance"],
            "product_results": serialise_products(simulation["products"]),
            "fuel_cost": simulation["fuel_cost"],
            "gross_profit": simulation["gross_profit"],
            "expenses": simulation["expenses"],
            "net_profit": simulation["net_profit"],
        },
    )

    return result