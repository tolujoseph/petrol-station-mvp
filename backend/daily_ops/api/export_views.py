"""Download a station's complete operational data, without authentication secrets."""
import csv
import io
import json
import tempfile
import zipfile
from pathlib import PurePosixPath

from django.core import serializers
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework.views import APIView

from .. import models
from .permissions import IsStationAdmin


class AdminExportView(APIView):
    permission_classes = [IsStationAdmin]

    def get(self, request):
        station = request.user.station
        output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        missing = []
        try:
            with transaction.atomic(), zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                groups = {
                    'stations': models.Station.objects.filter(id=station.id),
                    'pumps': models.Pump.objects.filter(station=station),
                    'tanks': models.Tank.objects.filter(station=station),
                    'columns': models.TransactionColumn.objects.filter(station=station),
                    'entries': models.DailyEntry.objects.filter(station=station),
                    'pump_readings': models.PumpReading.objects.filter(daily_entry__station=station),
                    'tank_readings': models.TankReading.objects.filter(daily_entry__station=station),
                    'transactions': models.FinancialTransaction.objects.filter(daily_entry__station=station),
                    'deliveries': models.FuelDelivery.objects.filter(tank__station=station),
                    'results': models.DailyResult.objects.filter(daily_entry__station=station),
                    'prices': models.ProductSettings.objects.filter(station=station),
                    'reconciliation_settings': models.ReconciliationSettings.objects.filter(station=station),
                    'edits': models.EntryEdit.objects.filter(entry__station=station),
                    'pump_photos': models.PumpReadingEvidence.objects.filter(pump_reading__daily_entry__station=station),
                    'tank_photos': models.TankReadingEvidence.objects.filter(tank_reading__daily_entry__station=station),
                }
                fixture = []
                counts = {}
                for name, queryset in groups.items():
                    rows = list(queryset.order_by('pk'))
                    counts[name] = len(rows)
                    fixture.extend(json.loads(serializers.serialize('json', rows)))
                    fields = [field.attname for field in queryset.model._meta.fields]
                    csv_file = io.StringIO(newline='')
                    writer = csv.writer(csv_file)
                    writer.writerow(fields)
                    for row in rows:
                        values = []
                        for field in fields:
                            value = getattr(row, field)
                            if isinstance(value, (list, dict)):
                                value = json.dumps(value, ensure_ascii=False)
                            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                                value = "'" + value
                            values.append(value)
                        writer.writerow(values)
                        if name in {'pump_photos', 'tank_photos'}:
                            image = row.image
                            path = PurePosixPath(image.name)
                            if not image.name or path.is_absolute() or '..' in path.parts:
                                missing.append(image.name)
                                continue
                            try:
                                with image.open('rb') as photo:
                                    archive.writestr('media/' + image.name, photo.read())
                            except FileNotFoundError:
                                missing.append(image.name)
                    archive.writestr(name + '.csv', '\ufeff' + csv_file.getvalue())
                users = list(models.User.objects.filter(station=station).values('id', 'username', 'first_name', 'last_name', 'role', 'is_staff', 'is_active'))
                archive.writestr('users.json', json.dumps(users, indent=2))
                archive.writestr('data.json', json.dumps(fixture, ensure_ascii=False, indent=2))
                archive.writestr('manifest.json', json.dumps({'format_version': 1, 'station': station.name, 'exported_at': timezone.now().isoformat(), 'counts': counts, 'missing_photos': missing}, indent=2))
                archive.writestr('README.txt', 'Station data export\n\nCSV files can be opened in Excel. IDs link rows between files.\ndata.json contains all operational records, drafts, older submissions, settings and edit history.\nmedia/ contains uploaded photos; manifest.json lists any missing files.\nusers.json identifies users without passwords or login sessions.\nThis download is a saved copy, not an automatic restore. Keep it somewhere safe before deploying.\n')
            output.seek(0)
            response = FileResponse(output, as_attachment=True, filename=f'station-backup-{station.id}-{timezone.now():%Y%m%d-%H%M%S}.zip', content_type='application/zip')
            response['Cache-Control'] = 'no-store'
            return response
        except Exception:
            output.close()
            raise
