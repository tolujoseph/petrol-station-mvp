
import uuid
from collections import defaultdict
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.dateparse import parse_date

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    User,
)
from ..services.orchestration import simulate_daily_entry, save_daily_result
from ..services.querysets import official_daily_entry_ids
from .permissions import IsManager
from .serializers import (
    DailyEntrySerializer,
    DailyResultSerializer,
    EvidenceUploadSerializer,
    PumpSerializer,
    ProductSettingsSerializer,
    ReconciliationSettingsSerializer,
    TankSerializer,
)


class CsrfTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        token = get_token(request)
        response = Response({"csrfToken": token})
        response["Cache-Control"] = "no-store"
        return response


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response({
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "station": user.station.name if user.station else None,
            "station_id": user.station_id,
        })


class StationEquipmentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.station_id:
            return Response(
                {"detail": "Your account is not assigned to a station."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        station = request.user.station

        pumps = Pump.objects.filter(station=station, active=True)
        tanks = Tank.objects.filter(station=station, active=True)

        return Response({
            "pumps": PumpSerializer(pumps, many=True).data,
            "tanks": TankSerializer(tanks, many=True).data,
        })


class StationProductSettingsView(APIView):
    """Read station product settings; owners may add effective-dated versions."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.station_id or request.user.role not in {
            User.Role.MANAGER, User.Role.OWNER
        }:
            raise Http404("Settings not found.")
        settings_rows = ProductSettings.objects.filter(
            station=request.user.station
        ).order_by("-effective_from", "product_type")
        return Response(ProductSettingsSerializer(settings_rows, many=True).data)

    def post(self, request):
        if not request.user.station_id or request.user.role != User.Role.OWNER:
            raise Http404("Settings not found.")
        serializer = ProductSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duplicate = ProductSettings.objects.filter(
            station=request.user.station,
            product_type=serializer.validated_data["product_type"],
            effective_from=serializer.validated_data["effective_from"],
        ).exists()
        if duplicate:
            raise ValidationError({
                "effective_from": "Settings already exist for this product and effective date."
            })
        instance = serializer.save(station=request.user.station)
        return Response(ProductSettingsSerializer(instance).data, status=status.HTTP_201_CREATED)


class StationReconciliationSettingsView(APIView):
    """Read station reconciliation settings; owners may add new versions."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.station_id or request.user.role not in {
            User.Role.MANAGER, User.Role.OWNER
        }:
            raise Http404("Settings not found.")
        settings_rows = ReconciliationSettings.objects.filter(
            station=request.user.station
        ).order_by("-effective_from")
        return Response(ReconciliationSettingsSerializer(settings_rows, many=True).data)

    def post(self, request):
        if not request.user.station_id or request.user.role != User.Role.OWNER:
            raise Http404("Settings not found.")
        serializer = ReconciliationSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duplicate = ReconciliationSettings.objects.filter(
            station=request.user.station,
            effective_from=serializer.validated_data["effective_from"],
        ).exists()
        if duplicate:
            raise ValidationError({
                "effective_from": "Reconciliation settings already exist for this effective date."
            })
        instance = serializer.save(station=request.user.station)
        return Response(ReconciliationSettingsSerializer(instance).data, status=status.HTTP_201_CREATED)


class DailyEntryCreateView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        """List the authenticated manager's resumable drafts."""
        drafts = DailyEntry.objects.filter(
            station=request.user.station,
            manager=request.user,
            status=DailyEntry.Status.DRAFT,
        ).order_by("-created_at")
        return Response([self.draft_summary(entry) for entry in drafts])

    @staticmethod
    def draft_summary(entry):
        return {
            "id": entry.id,
            "entry_date": entry.entry_date,
            "status": entry.status,
            "notes": entry.notes,
            "created_at": entry.created_at,
            "pump_count": entry.pump_readings.count(),
            "tank_count": entry.tank_readings.count(),
            "financial_transaction_count": entry.financial_transactions.count(),
        }

    def post(self, request):
        serializer = DailyEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_key = request.headers.get("Idempotency-Key")
        idempotency_key = None

        if raw_key:
            try:
                idempotency_key = uuid.UUID(raw_key)
            except (ValueError, TypeError, AttributeError):
                raise ValidationError({
                    "Idempotency-Key": "Provide a valid UUID."
                })

        station = request.user.station

        if idempotency_key:
            existing = DailyEntry.objects.filter(
                station=station,
                idempotency_key=idempotency_key,
            ).first()

            if existing:
                return self.entry_response(existing, replayed=True)

        data = serializer.validated_data
        pump_inputs = data.pop("pump_readings")
        tank_inputs = data.pop("tank_readings")
        transaction_inputs = data.pop("financial_transactions", [])
        entry_date = data.pop("entry_date", timezone.localdate())
        notes = data.pop("notes", "")

        pump_ids = [item["pump"].id for item in pump_inputs]
        tank_ids = [item["tank"].id for item in tank_inputs]

        if Pump.objects.filter(
            id__in=pump_ids,
            station=station,
            active=True,
        ).count() != len(set(pump_ids)):
            raise ValidationError({
                "pump_readings": (
                    "One or more pumps are invalid for this station."
                )
            })

        if Tank.objects.filter(
            id__in=tank_ids,
            station=station,
            active=True,
        ).count() != len(set(tank_ids)):
            raise ValidationError({
                "tank_readings": (
                    "One or more tanks are invalid for this station."
                )
            })

        try:
            with transaction.atomic():
                entry = DailyEntry.objects.create(
                    station=station,
                    manager=request.user,
                    entry_date=entry_date,
                    idempotency_key=idempotency_key,
                    status=DailyEntry.Status.DRAFT,
                    notes=notes,
                )

                pump_reading_ids = []
                tank_reading_ids = []

                for item in pump_inputs:
                    reading = PumpReading.objects.create(
                        daily_entry=entry,
                        pump=item["pump"],
                        closing_reading=item["closing_reading"],
                    )
                    pump_reading_ids.append(reading.id)

                for item in tank_inputs:
                    reading = TankReading.objects.create(
                        daily_entry=entry,
                        tank=item["tank"],
                        closing_reading=item["closing_reading"],
                    )
                    tank_reading_ids.append(reading.id)

                for item in transaction_inputs:
                    FinancialTransaction.objects.create(
                        daily_entry=entry,
                        **item,
                    )

        except IntegrityError:
            if idempotency_key:
                existing = DailyEntry.objects.filter(
                    station=station,
                    idempotency_key=idempotency_key,
                ).first()

                if existing:
                    return self.entry_response(existing, replayed=True)

            raise

        return Response({
            "id": entry.id,
            "entry_date": entry.entry_date,
            "status": entry.status,
            "notes": entry.notes,
            "pump_reading_ids": pump_reading_ids,
            "tank_reading_ids": tank_reading_ids,
            "replayed": False,
        }, status=status.HTTP_201_CREATED)

    @staticmethod
    def entry_response(entry, replayed=False):
        return Response({
            "id": entry.id,
            "entry_date": entry.entry_date,
            "status": entry.status,
            "notes": entry.notes,
            "pump_reading_ids": list(
                entry.pump_readings.order_by("id").values_list(
                    "id", flat=True
                )
            ),
            "tank_reading_ids": list(
                entry.tank_readings.order_by("id").values_list(
                    "id", flat=True
                )
            ),
            "replayed": replayed,
        }, status=status.HTTP_200_OK)


def schedule_evidence_file_deletion(evidence_rows):
    """Delete stored image files after the surrounding DB transaction commits."""
    for evidence in evidence_rows:
        image = getattr(evidence, "image", None)
        if image and image.name:
            storage = image.storage
            name = image.name
            transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))


class DailyEntryDetailView(APIView):
    """Retrieve, update, or explicitly discard a manager-owned draft."""
    permission_classes = [IsManager]

    def get_entry(self, request, entry_id):
        entry = DailyEntry.objects.filter(
            id=entry_id,
            station=request.user.station,
            manager=request.user,
        ).first()
        if entry is None:
            raise Http404("Daily entry not found.")
        return entry

    def get(self, request, entry_id):
        entry = self.get_entry(request, entry_id)
        return Response(self.entry_detail(entry))

    @staticmethod
    def entry_detail(entry):
        return {
            "id": entry.id,
            "entry_date": entry.entry_date,
            "status": entry.status,
            "notes": entry.notes,
            "pump_readings": [
                {
                    "id": reading.id,
                    "pump": reading.pump_id,
                    "label": reading.pump.label,
                    "product_type": reading.pump.product_type,
                    "closing_reading": str(reading.closing_reading),
                    "evidence_count": reading.evidence_photos.count(),
                }
                for reading in entry.pump_readings.select_related("pump").order_by("id")
            ],
            "tank_readings": [
                {
                    "id": reading.id,
                    "tank": reading.tank_id,
                    "label": reading.tank.label,
                    "product_type": reading.tank.product_type,
                    "closing_reading": str(reading.closing_reading),
                    "evidence_count": reading.evidence_photos.count(),
                }
                for reading in entry.tank_readings.select_related("tank").order_by("id")
            ],
            "financial_transactions": [
                {
                    "id": item.id,
                    "product_type": item.product_type,
                    "transaction_type": item.transaction_type,
                    "amount": str(item.amount),
                    "description": item.description,
                }
                for item in entry.financial_transactions.order_by("id")
            ],
        }

    def patch(self, request, entry_id):
        with transaction.atomic():
            entry = DailyEntry.objects.select_for_update().filter(
                id=entry_id,
                station=request.user.station,
                manager=request.user,
                status=DailyEntry.Status.DRAFT,
            ).first()
            if entry is None:
                raise Http404("Editable draft not found.")

            serializer = DailyEntrySerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data

            pump_inputs = data.pop("pump_readings", None)
            tank_inputs = data.pop("tank_readings", None)
            transaction_inputs = data.pop("financial_transactions", None)

            if "entry_date" in data:
                entry.entry_date = data["entry_date"]
            if "notes" in data:
                entry.notes = data["notes"]
            entry.save(update_fields=["entry_date", "notes"])

            if pump_inputs is not None:
                pump_ids = [item["pump"].id for item in pump_inputs]
                if Pump.objects.filter(
                    id__in=pump_ids, station=request.user.station, active=True
                ).count() != len(set(pump_ids)):
                    raise ValidationError({"pump_readings": "One or more pumps are invalid for this station."})
                existing = {row.pump_id: row for row in entry.pump_readings.select_related("pump")}
                incoming_ids = set(pump_ids)
                removed_readings = entry.pump_readings.exclude(pump_id__in=incoming_ids)
                removed_evidence = [evidence for reading in removed_readings for evidence in reading.evidence_photos.all()]
                schedule_evidence_file_deletion(removed_evidence)
                removed_readings.delete()
                for item in pump_inputs:
                    pump_id = item["pump"].id
                    row = existing.get(pump_id)
                    if row:
                        row.closing_reading = item["closing_reading"]
                        row.save(update_fields=["closing_reading"])
                    else:
                        PumpReading.objects.create(daily_entry=entry, **item)

            if tank_inputs is not None:
                tank_ids = [item["tank"].id for item in tank_inputs]
                if Tank.objects.filter(
                    id__in=tank_ids, station=request.user.station, active=True
                ).count() != len(set(tank_ids)):
                    raise ValidationError({"tank_readings": "One or more tanks are invalid for this station."})
                existing = {row.tank_id: row for row in entry.tank_readings.select_related("tank")}
                incoming_ids = set(tank_ids)
                removed_readings = entry.tank_readings.exclude(tank_id__in=incoming_ids)
                removed_evidence = [evidence for reading in removed_readings for evidence in reading.evidence_photos.all()]
                schedule_evidence_file_deletion(removed_evidence)
                removed_readings.delete()
                for item in tank_inputs:
                    tank_id = item["tank"].id
                    row = existing.get(tank_id)
                    if row:
                        row.closing_reading = item["closing_reading"]
                        row.save(update_fields=["closing_reading"])
                    else:
                        TankReading.objects.create(daily_entry=entry, **item)

            if transaction_inputs is not None:
                entry.financial_transactions.all().delete()
                FinancialTransaction.objects.bulk_create([
                    FinancialTransaction(daily_entry=entry, **item)
                    for item in transaction_inputs
                ])

        return Response(self.entry_detail(entry))

    def delete(self, request, entry_id):
        with transaction.atomic():
            entry = DailyEntry.objects.select_for_update().filter(
                id=entry_id,
                station=request.user.station,
                manager=request.user,
            ).first()
            if entry is None:
                raise Http404("Daily entry not found.")
            if entry.status != DailyEntry.Status.DRAFT:
                raise ValidationError("Only a draft can be discarded.")
            evidence_rows = list(PumpReadingEvidence.objects.filter(
                pump_reading__daily_entry=entry
            )) + list(TankReadingEvidence.objects.filter(
                tank_reading__daily_entry=entry
            ))
            schedule_evidence_file_deletion(evidence_rows)
            entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EvidenceUploadBaseView(APIView):
    permission_classes = [IsManager]
    parser_classes = [MultiPartParser, FormParser]

    evidence_model = None
    reading_model = None
    reading_relation = None
    input_serializer_class = None

    def post(self, request, reading_id):
        serializer = self.input_serializer_class(data={
            "images": request.FILES.getlist("images")
        })
        serializer.is_valid(raise_exception=True)

        reading = self.reading_model.objects.select_related(
            "daily_entry"
        ).filter(
            id=reading_id,
            daily_entry__station=request.user.station,
            daily_entry__manager=request.user,
            daily_entry__status=DailyEntry.Status.DRAFT,
        ).first()

        if reading is None:
            raise Http404("Draft reading not found.")

        evidence_rows = [
            self.evidence_model(
                **{self.reading_relation: reading},
                image=image,
                uploaded_by=request.user,
            )
            for image in serializer.validated_data["images"]
        ]

        self.evidence_model.objects.bulk_create(evidence_rows)

        return Response({
            "message": "Evidence uploaded successfully.",
            "uploaded_count": len(evidence_rows),
        }, status=status.HTTP_201_CREATED)


class PumpEvidenceUploadView(EvidenceUploadBaseView):
    evidence_model = PumpReadingEvidence
    reading_model = PumpReading
    reading_relation = "pump_reading"
    input_serializer_class = EvidenceUploadSerializer


class TankEvidenceUploadView(EvidenceUploadBaseView):
    evidence_model = TankReadingEvidence
    reading_model = TankReading
    reading_relation = "tank_reading"
    input_serializer_class = EvidenceUploadSerializer

class FinaliseDailyEntryView(APIView):
    permission_classes = [IsManager]

    def post(self, request, entry_id):
        with transaction.atomic():
            entry = DailyEntry.objects.select_for_update().filter(
                id=entry_id,
                station=request.user.station,
                manager=request.user,
            ).first()

            if entry is None:
                raise Http404("Daily entry not found.")

            if entry.status == DailyEntry.Status.SUBMITTED:
                return Response({
                    "id": entry.id,
                    "status": entry.status,
                    "message": "This entry has already been submitted.",
                })

            try:
                simulation = simulate_daily_entry(entry)
                save_daily_result(entry, simulation)
            except ValueError as exc:
                raise APIException(
                    f"Reconciliation calculation failed: {exc}"
                ) from exc

            entry.status = DailyEntry.Status.SUBMITTED
            entry.submitted_at = timezone.now()
            entry.save(update_fields=["status", "submitted_at"])

        return Response({
            "id": entry.id,
            "status": entry.status,
            "message": "Daily entry submitted successfully.",
        })



class EvidenceImageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, evidence_type, evidence_id):
        if not request.user.station_id:
            raise Http404("Evidence not found.")

        if evidence_type == "pump":
            evidence = PumpReadingEvidence.objects.select_related(
                "pump_reading__daily_entry"
            ).filter(
                id=evidence_id,
                pump_reading__daily_entry__station=request.user.station,
            ).first()

            entry = evidence.pump_reading.daily_entry if evidence else None

        elif evidence_type == "tank":
            evidence = TankReadingEvidence.objects.select_related(
                "tank_reading__daily_entry"
            ).filter(
                id=evidence_id,
                tank_reading__daily_entry__station=request.user.station,
            ).first()

            entry = evidence.tank_reading.daily_entry if evidence else None

        else:
            raise Http404("Evidence not found.")

        if evidence is None or entry is None:
            raise Http404("Evidence not found.")

        if request.user.role == User.Role.MANAGER:
            if entry.manager_id != request.user.id:
                raise Http404("Evidence not found.")
        elif request.user.role == User.Role.OWNER:
            if entry.status != DailyEntry.Status.SUBMITTED:
                raise Http404("Evidence not found.")
        else:
            raise Http404("Evidence not found.")

        response = FileResponse(evidence.image.open("rb"))
        response["Cache-Control"] = "private, no-store"
        return response


def parse_report_date(value, field_name):
    try:
        parsed_date = parse_date(value)
    except ValueError:
        parsed_date = None

    if parsed_date is None:
        raise ValidationError({
            field_name: "Use a valid date in YYYY-MM-DD format."
        })

    return parsed_date


def apply_report_date_filters(queryset, query_params):
    selected_date_value = query_params.get("date")
    start_value = query_params.get("start_date")
    end_value = query_params.get("end_date")

    if selected_date_value and (start_value or end_value):
        raise ValidationError({
            "date": "Use either date or a date range, not both."
        })

    if selected_date_value:
        selected_date = parse_report_date(
            selected_date_value, "date"
        )
        return queryset.filter(
            daily_entry__entry_date=selected_date
        )

    start_date = (
        parse_report_date(start_value, "start_date")
        if start_value else None
    )
    end_date = (
        parse_report_date(end_value, "end_date")
        if end_value else None
    )

    if start_date and end_date and start_date > end_date:
        raise ValidationError({
            "start_date": "Start date cannot be after end date."
        })

    if start_date:
        queryset = queryset.filter(
            daily_entry__entry_date__gte=start_date
        )

    if end_date:
        queryset = queryset.filter(
            daily_entry__entry_date__lte=end_date
        )

    return queryset


REPORT_METRICS = (
    "pump_volume",
    "tank_movement",
    "physical_difference",
    "expected_revenue",
    "actual_sales",
    "financial_difference",
    "fuel_cost",
    "gross_profit",
    "expenses",
    "net_profit",
)


def aggregate_daily_results(results, group_by):
    """
    Sum saved DailyResult values by day, month or year.

    The queryset must already be filtered to official results from
    the authenticated user's station and the requested date range.
    """
    grouped = defaultdict(
        lambda: {
            "entry_count": 0,
            **{
                metric: Decimal("0.00")
                for metric in REPORT_METRICS
            },
        }
    )

    for result in results:
        entry_date = result.daily_entry.entry_date

        if group_by == "day":
            period = entry_date.isoformat()
        elif group_by == "month":
            period = entry_date.strftime("%Y-%m")
        else:
            period = str(entry_date.year)

        summary = grouped[period]
        summary["entry_count"] += 1

        for metric in REPORT_METRICS:
            summary[metric] += (
                getattr(result, metric) or Decimal("0.00")
            )

    return [
        {
            "period": period,
            "entry_count": values["entry_count"],
            **{
                metric: f"{values[metric]:.2f}"
                for metric in REPORT_METRICS
            },
        }
        for period, values in sorted(
            grouped.items(),
            reverse=True,
        )
    ]


class DailyResultListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.station_id:
            if request.query_params.get("group_by"):
                return Response({
                    "group_by": request.query_params.get("group_by"),
                    "results": [],
                })
            return Response([])

        group_by = request.query_params.get("group_by")

        if group_by and group_by not in {"day", "month", "year"}:
            raise ValidationError({
                "group_by": "Choose day, month or year."
            })

        official_entry_ids = official_daily_entry_ids(
            request.user.station
        )

        results = DailyResult.objects.filter(
            daily_entry__station=request.user.station,
            daily_entry_id__in=official_entry_ids,
        ).select_related(
            "daily_entry"
        ).order_by(
            "-daily_entry__entry_date",
            "-daily_entry__created_at",
        )

        results = apply_report_date_filters(
            results,
            request.query_params,
        )

        if group_by:
            return Response({
                "group_by": group_by,
                "results": aggregate_daily_results(results, group_by),
            })

        return Response(
            DailyResultSerializer(results, many=True).data
        )


class DiscrepancyReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.station_id:
            return Response([])

        official_entry_ids = official_daily_entry_ids(
            request.user.station
        )

        results = DailyResult.objects.filter(
            daily_entry__station=request.user.station,
            daily_entry_id__in=official_entry_ids,
        ).filter(
            Q(physical_difference__gt=0)
            | Q(physical_difference__lt=0)
            | Q(financial_difference__gt=0)
            | Q(financial_difference__lt=0)
        ).select_related(
            "daily_entry"
        ).order_by(
            "-daily_entry__entry_date",
            "-daily_entry__created_at",
        )

        results = apply_report_date_filters(
            results,
            request.query_params,
        )

        return Response(
            DailyResultSerializer(results, many=True).data
        )
