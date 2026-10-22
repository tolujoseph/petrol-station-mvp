
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class Station(models.Model):
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        OWNER = "owner", "Owner"

    station = models.ForeignKey(
        Station,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MANAGER,
    )

    def __str__(self):
        return self.username


class Pump(models.Model):
    class ProductType(models.TextChoices):
        PMS = "PMS", "PMS"
        AGO = "AGO", "AGO"

    station = models.ForeignKey(
        Station, on_delete=models.CASCADE, related_name="pumps"
    )
    label = models.CharField(max_length=100)
    product_type = models.CharField(max_length=10, choices=ProductType.choices)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.station.name} - {self.label}"


class Tank(models.Model):
    class ProductType(models.TextChoices):
        PMS = "PMS", "PMS"
        AGO = "AGO", "AGO"

    station = models.ForeignKey(
        Station, on_delete=models.CASCADE, related_name="tanks"
    )
    label = models.CharField(max_length=100)
    product_type = models.CharField(max_length=10, choices=ProductType.choices)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.station.name} - {self.label}"


class DailyEntry(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"

    station = models.ForeignKey(
        Station, on_delete=models.CASCADE, related_name="daily_entries"
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="daily_entries",
    )
    entry_date = models.DateField()
    idempotency_key = models.UUIDField(null=True, blank=True, editable=False)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["station", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_station_entry_idempotency_key",
            ),
        ]

    def __str__(self):
        return f"{self.station.name} - {self.entry_date} - {self.pk}"


class PumpReading(models.Model):
    daily_entry = models.ForeignKey(
        DailyEntry, on_delete=models.CASCADE, related_name="pump_readings"
    )
    pump = models.ForeignKey(
        Pump, on_delete=models.PROTECT, related_name="readings"
    )
    closing_reading = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["daily_entry", "pump"],
                name="unique_pump_per_daily_entry",
            ),
        ]

    def __str__(self):
        return f"{self.pump.label}: {self.closing_reading}"


class TankReading(models.Model):
    daily_entry = models.ForeignKey(
        DailyEntry, on_delete=models.CASCADE, related_name="tank_readings"
    )
    tank = models.ForeignKey(
        Tank, on_delete=models.PROTECT, related_name="readings"
    )
    closing_reading = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["daily_entry", "tank"],
                name="unique_tank_per_daily_entry",
            ),
        ]

    def __str__(self):
        return f"{self.tank.label}: {self.closing_reading}"


class PumpReadingEvidence(models.Model):
    pump_reading = models.ForeignKey(
        PumpReading, on_delete=models.CASCADE, related_name="evidence_photos"
    )
    image = models.ImageField(upload_to="reading_evidence/pumps/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_pump_evidence",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)


class TankReadingEvidence(models.Model):
    tank_reading = models.ForeignKey(
        TankReading, on_delete=models.CASCADE, related_name="evidence_photos"
    )
    image = models.ImageField(upload_to="reading_evidence/tanks/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_tank_evidence",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)


class FuelDelivery(models.Model):
    tank = models.ForeignKey(
        Tank, on_delete=models.PROTECT, related_name="deliveries"
    )
    delivery_date = models.DateField()
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tank.label} - {self.quantity}"


class FinancialTransaction(models.Model):
    class ProductType(models.TextChoices):
        PMS = "PMS", "PMS"
        AGO = "AGO", "AGO"

    class TransactionType(models.TextChoices):
        POS = "POS", "POS"
        CASH_BANK = "cash_bank", "Cash / Bank"
        CREDIT = "CREDIT", "Credit"
        EXPENSE = "expense", "Expense"
        TRANSFER = "transfer", "Transfer"
        SHELL_DEPOSIT = "shell_deposit", "Shell Deposit"

    daily_entry = models.ForeignKey(
        DailyEntry,
        on_delete=models.CASCADE,
        related_name="financial_transactions",
    )
    product_type = models.CharField(
        max_length=10, choices=ProductType.choices, blank=True
    )
    transaction_type = models.CharField(
        max_length=30, choices=TransactionType.choices
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.transaction_type}: {self.amount}"


class ProductSettings(models.Model):
    class ProductType(models.TextChoices):
        PMS = "PMS", "PMS"
        AGO = "AGO", "AGO"

    station = models.ForeignKey(
        Station, on_delete=models.CASCADE, related_name="product_settings"
    )
    product_type = models.CharField(max_length=10, choices=ProductType.choices)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    landing_cost = models.DecimalField(max_digits=12, decimal_places=2)
    effective_from = models.DateField()

    class Meta:
        ordering = ["-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["station", "product_type", "effective_from"],
                name="unique_product_settings_effective_date",
            ),
        ]


class ReconciliationSettings(models.Model):
    station = models.ForeignKey(
        Station, on_delete=models.CASCADE, related_name="reconciliation_settings"
    )
    adjustment_divisor = models.DecimalField(
        max_digits=12, decimal_places=4, default=20
    )
    adjustment_factor = models.DecimalField(
        max_digits=12, decimal_places=4, default=0.85
    )
    physical_tolerance = models.DecimalField(
        max_digits=12, decimal_places=4, default=5.00
    )
    # Kept separate from physical reconciliation. Its validation semantics
    # are intentionally not applied until the business rule is confirmed.
    adjustment_tolerance = models.DecimalField(
        max_digits=12, decimal_places=4, default=0.05
    )
    effective_from = models.DateField()

    class Meta:
        ordering = ["-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["station", "effective_from"],
                name="unique_reconciliation_settings_effective_date",
            ),
        ]


class DailyResult(models.Model):
    daily_entry = models.OneToOneField(
        DailyEntry, on_delete=models.CASCADE, related_name="result"
    )
    pump_volume = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tank_movement = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    physical_difference = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    # Nullable for results calculated before this outcome was persisted.
    physical_within_tolerance = models.BooleanField(null=True, blank=True)
    expected_revenue = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    actual_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    financial_difference = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    fuel_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gross_profit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expenses = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_profit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    calculated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Result for entry {self.daily_entry_id}"
