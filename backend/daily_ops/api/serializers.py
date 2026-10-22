
from rest_framework import serializers

from ..models import (
    DailyEntry,
    DailyResult,
    FinancialTransaction,
    ProductSettings,
    ReconciliationSettings,
    Pump,
    PumpReading,
    PumpReadingEvidence,
    Tank,
    TankReading,
    TankReadingEvidence,
)


MAX_IMAGE_SIZE = 10 * 1024 * 1024


class PumpReadingInputSerializer(serializers.ModelSerializer):
    closing_reading = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0
    )

    class Meta:
        model = PumpReading
        fields = ["pump", "closing_reading"]


class TankReadingInputSerializer(serializers.ModelSerializer):
    closing_reading = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0
    )

    class Meta:
        model = TankReading
        fields = ["tank", "closing_reading"]


class FinancialTransactionInputSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0
    )

    class Meta:
        model = FinancialTransaction
        fields = [
            "product_type",
            "transaction_type",
            "amount",
            "description",
        ]


class DailyEntrySerializer(serializers.ModelSerializer):
    pump_readings = PumpReadingInputSerializer(many=True)
    tank_readings = TankReadingInputSerializer(many=True)
    financial_transactions = FinancialTransactionInputSerializer(many=True)

    class Meta:
        model = DailyEntry
        fields = [
            "entry_date",
            "notes",
            "pump_readings",
            "tank_readings",
            "financial_transactions",
        ]

    def validate_pump_readings(self, readings):
        ids = [item["pump"].id for item in readings]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "Each pump can only be submitted once per daily entry."
            )
        return readings

    def validate_tank_readings(self, readings):
        ids = [item["tank"].id for item in readings]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "Each tank can only be submitted once per daily entry."
            )
        return readings

    def validate(self, attrs):
        # Full draft creation must contain readings for both equipment types.
        # Partial updates may update only notes/date, so validate only fields
        # supplied in that request.
        if not self.partial or "pump_readings" in attrs:
            if not attrs.get("pump_readings"):
                raise serializers.ValidationError({
                    "pump_readings": "At least one pump reading is required."
                })
        if not self.partial or "tank_readings" in attrs:
            if not attrs.get("tank_readings"):
                raise serializers.ValidationError({
                    "tank_readings": "At least one tank reading is required."
                })
        return attrs


class EvidenceUploadSerializer(serializers.Serializer):
    images = serializers.ListField(
        child=serializers.ImageField(),
        allow_empty=False,
    )

    def validate_images(self, images):
        for image in images:
            if image.size > MAX_IMAGE_SIZE:
                raise serializers.ValidationError(
                    "Each image must be 10 MB or smaller."
                )
        return images


class PumpEvidenceSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.CharField(
        source="uploaded_by.username",
        read_only=True,
    )

    class Meta:
        model = PumpReadingEvidence
        fields = ["id", "uploaded_by", "uploaded_at"]


class TankEvidenceSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.CharField(
        source="uploaded_by.username",
        read_only=True,
    )

    class Meta:
        model = TankReadingEvidence
        fields = ["id", "uploaded_by", "uploaded_at"]


class PumpSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pump
        fields = ["id", "label", "product_type", "active"]


class TankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tank
        fields = ["id", "label", "product_type", "active"]


class DailyResultSerializer(serializers.ModelSerializer):
    station = serializers.CharField(
        source="daily_entry.station.name",
        read_only=True,
    )
    entry_date = serializers.DateField(
        source="daily_entry.entry_date",
        read_only=True,
    )

    class Meta:
        model = DailyResult
        fields = [
            "id",
            "station",
            "entry_date",
            "pump_volume",
            "tank_movement",
            "physical_difference",
            "physical_within_tolerance",
            "expected_revenue",
            "actual_sales",
            "financial_difference",
            "fuel_cost",
            "gross_profit",
            "expenses",
            "net_profit",
            "calculated_at",
        ]


class ProductSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSettings
        fields = [
            "id", "product_type", "selling_price", "landing_cost", "effective_from"
        ]
        read_only_fields = ["id"]

    def validate_selling_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Selling price cannot be negative.")
        return value

    def validate_landing_cost(self, value):
        if value < 0:
            raise serializers.ValidationError("Landing cost cannot be negative.")
        return value


class ReconciliationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationSettings
        fields = [
            "id", "adjustment_divisor", "adjustment_factor",
            "physical_tolerance", "adjustment_tolerance", "effective_from",
        ]
        read_only_fields = ["id"]

    def validate_adjustment_divisor(self, value):
        if value <= 0:
            raise serializers.ValidationError("Adjustment divisor must be greater than zero.")
        return value

    def validate_adjustment_factor(self, value):
        if value < 0:
            raise serializers.ValidationError("Adjustment factor cannot be negative.")
        return value

    def validate_physical_tolerance(self, value):
        if value < 0:
            raise serializers.ValidationError("Physical tolerance cannot be negative.")
        return value

    def validate_adjustment_tolerance(self, value):
        if value < 0:
            raise serializers.ValidationError("Adjustment tolerance cannot be negative.")
        return value
