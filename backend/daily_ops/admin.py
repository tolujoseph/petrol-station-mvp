from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    DailyEntry,
    DailyResult,
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


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "created_at")


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Daily Ops",
            {
                "fields": ("station", "role"),
            },
        ),
    )

@admin.register(Pump)
class PumpAdmin(admin.ModelAdmin):
    list_display = ("label", "station", "product_type", "active")
    list_filter = ("station", "product_type", "active")


@admin.register(Tank)
class TankAdmin(admin.ModelAdmin):
    list_display = ("label", "station", "product_type", "active")
    list_filter = ("station", "product_type", "active")

@admin.register(DailyEntry)
class DailyEntryAdmin(admin.ModelAdmin):
    list_display = (
        "station",
        "manager",
        "entry_date",
        "submitted_at",
        "created_at",
    )
    list_filter = ("station", "entry_date")
    search_fields = ("station__name", "manager__username")

@admin.register(PumpReading)
class PumpReadingAdmin(admin.ModelAdmin):
    list_display = (
        "daily_entry",
        "pump",
        "closing_reading",
    )
    list_filter = ("pump__station", "pump__product_type")

@admin.register(TankReading)
class TankReadingAdmin(admin.ModelAdmin):
    list_display = (
        "daily_entry",
        "tank",
        "closing_reading",
    )
    list_filter = ("tank__station", "tank__product_type")

@admin.register(FuelDelivery)
class FuelDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "tank",
        "delivery_date",
        "quantity",
        "created_at",
    )
    list_filter = ("delivery_date", "tank__station")

@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "daily_entry",
        "product_type",
        "transaction_type",
        "amount",
        "description",
    )
    list_filter = (
        "product_type",
        "transaction_type",
        "daily_entry__station",
    )

@admin.register(ProductSettings)
class ProductSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "station",
        "product_type",
        "selling_price",
        "landing_cost",
        "effective_from",
    )
    list_filter = ("station", "product_type")

@admin.register(ReconciliationSettings)
class ReconciliationSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "station",
        "adjustment_divisor",
        "adjustment_factor",
        "physical_tolerance",
        "adjustment_tolerance",
        "effective_from",
    )
    list_filter = ("station",)

@admin.register(DailyResult)
class DailyResultAdmin(admin.ModelAdmin):
    list_display = (
        "daily_entry",
        "pump_volume",
        "tank_movement",
        "physical_difference",
        "physical_within_tolerance",
        "expected_revenue",
        "actual_sales",
        "financial_difference",
        "gross_profit",
        "net_profit",
        "calculated_at",
    )
    list_filter = ("daily_entry__station",)