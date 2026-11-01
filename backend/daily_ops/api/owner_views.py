"""Station configuration and submitted-entry corrections, scoped to one station."""
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Max
from django.http import Http404
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import DailyEntry, EntryEdit, FinancialTransaction, Pump, Tank, TransactionColumn, User
from ..services.orchestration import save_daily_result, simulate_daily_entry
from ..services.querysets import official_daily_entry_ids
from .permissions import IsOwner
from .serializers import DailyEntrySerializer, PumpSerializer, TankSerializer, TransactionColumnSerializer
from .views import DailyEntryDetailView, parse_report_date


class ColumnsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.station_id:
            raise Http404()
        return Response(TransactionColumnSerializer(TransactionColumn.objects.filter(station=request.user.station), many=True).data)

    def post(self, request):
        if not IsOwner().has_permission(request, self):
            raise PermissionDenied()
        serializer = TransactionColumnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if TransactionColumn.objects.filter(station=request.user.station, label__iexact=serializer.validated_data['label']).exists():
            raise ValidationError({"label": "A column with this name already exists. You can restore it if hidden."})
        position = (TransactionColumn.objects.filter(station=request.user.station).aggregate(value=Max('position'))['value'] or 0) + 1
        serializer.save(station=request.user.station, position=position)
        return Response(serializer.data, status=201)


class ColumnDetailView(APIView):
    permission_classes = [IsOwner]

    def patch(self, request, column_id):
        row = TransactionColumn.objects.filter(station=request.user.station, id=column_id).first()
        if row is None:
            raise Http404()
        # Keep names and accounting meanings stable in historical records.
        if set(request.data) != {'active'}:
            raise ValidationError("Only visibility can be changed. Create a new column for a different name or type.")
        serializer = TransactionColumnSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class EquipmentSettingsView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        return Response({
            'pumps': PumpSerializer(Pump.objects.filter(station=request.user.station), many=True).data,
            'tanks': TankSerializer(Tank.objects.filter(station=request.user.station), many=True).data,
        })

    def post(self, request):
        kind = request.data.get('kind')
        if kind not in {'pump', 'tank'}:
            raise ValidationError({'kind': 'Choose pump or tank.'})
        model, serializer_class = (Pump, PumpSerializer) if kind == 'pump' else (Tank, TankSerializer)
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if model.objects.filter(station=request.user.station, label__iexact=data['label'], product_type=data['product_type']).exists():
            raise ValidationError({'label': 'This equipment already exists. Restore it if hidden.'})
        serializer.save(station=request.user.station)
        return Response(serializer.data, status=201)


class EquipmentVisibilityView(APIView):
    permission_classes = [IsOwner]

    def patch(self, request, kind, equipment_id):
        if kind not in {'pump', 'tank'}:
            raise Http404()
        model, serializer_class = (Pump, PumpSerializer) if kind == 'pump' else (Tank, TankSerializer)
        row = model.objects.filter(station=request.user.station, id=equipment_id).first()
        if row is None:
            raise Http404()
        if set(request.data) != {'active'}:
            raise ValidationError('Only visibility can be changed.')
        serializer = serializer_class(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SavedEntryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entry_id=None):
        if not request.user.station_id:
            raise Http404()
        entries = DailyEntry.objects.filter(station=request.user.station, status=DailyEntry.Status.SUBMITTED)
        if request.user.role == User.Role.MANAGER:
            entries = entries.filter(manager=request.user)
        elif request.user.role != User.Role.OWNER:
            raise PermissionDenied()
        if entry_id is not None:
            entry = entries.filter(id=entry_id).first()
        else:
            day = parse_report_date(request.query_params.get('date'), 'date')
            entry = entries.filter(entry_date=day).order_by('-submitted_at', '-id').first()
        if entry is None:
            raise Http404('No submitted entry found for this date.')
        return Response(DailyEntryDetailView.entry_detail(entry))

    def patch(self, request, entry_id):
        if not IsOwner().has_permission(request, self):
            raise PermissionDenied()
        with transaction.atomic():
            entry = DailyEntry.objects.select_for_update().filter(id=entry_id, station=request.user.station, status=DailyEntry.Status.SUBMITTED).first()
            if entry is None:
                raise Http404()
            if entry.id not in official_daily_entry_ids(request.user.station):
                raise ValidationError('A newer entry exists for this date. Open the latest entry from History.')
            if request.data.get('version') != entry.edits.count():
                return Response({'detail': 'This entry has changed. Close it and reopen before editing.'}, status=409)
            if 'entry_date' in request.data and str(request.data['entry_date']) != entry.entry_date.isoformat():
                raise ValidationError('The date of a submitted entry cannot be changed.')
            serializer = DailyEntrySerializer(data=request.data, partial=True, context={'request': request, 'entry': entry})
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            before = json.loads(json.dumps(DailyEntryDetailView.entry_detail(entry), cls=DjangoJSONEncoder))
            # Correct existing readings in place, preserving equipment and photo associations.
            for field, relation, key in [('pump_readings', entry.pump_readings, 'pump'), ('tank_readings', entry.tank_readings, 'tank')]:
                if field not in data:
                    continue
                rows = {getattr(row, key + '_id'): row for row in relation.all()}
                if set(rows) != {item[key].id for item in data[field]}:
                    raise ValidationError({field: 'Corrections must retain the equipment originally recorded.'})
                for item in data[field]:
                    row = rows[item[key].id]
                    row.closing_reading = item['closing_reading']
                    fields = ['closing_reading']
                    if key == 'tank':
                        row.delivered_quantity = item.get('delivered_quantity', row.delivered_quantity)
                        fields.append('delivered_quantity')
                    row.save(update_fields=fields)
            if 'financial_transactions' in data:
                entry.financial_transactions.all().delete()
                FinancialTransaction.objects.bulk_create([FinancialTransaction(daily_entry=entry, **item) for item in data['financial_transactions']])
            if 'notes' in data:
                entry.notes = data['notes']
                entry.save(update_fields=['notes'])
            # Later days derive opening readings from earlier days. Refresh them atomically too.
            following = DailyEntry.objects.filter(id__in=official_daily_entry_ids(entry.station), entry_date__gte=entry.entry_date).order_by('entry_date')
            try:
                for affected in following:
                    save_daily_result(affected, simulate_daily_entry(affected))
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            EntryEdit.objects.create(entry=entry, edited_by=request.user, before=before)
        return Response(DailyEntryDetailView.entry_detail(entry))
