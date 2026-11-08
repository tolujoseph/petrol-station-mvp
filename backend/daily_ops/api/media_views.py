import io
import json
import tempfile
import zipfile
from pathlib import PurePosixPath

from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from ..models import PumpReadingEvidence, TankReadingEvidence, MediaDeletionJob
from ..media import process_deletion
from .permissions import IsStationAdmin
from .views import EvidenceImageView, parse_report_date

MODELS = {'pump': (PumpReadingEvidence, 'pump_reading'), 'tank': (TankReadingEvidence, 'tank_reading')}


def media_rows(station, before=None):
    for kind, (model, relation) in MODELS.items():
        rows = model.objects.filter(**{relation + '__daily_entry__station': station}).select_related(relation + '__daily_entry', relation + '__' + kind, 'uploaded_by')
        if before:
            rows = rows.filter(**{relation + '__daily_entry__entry_date__lte': before})
        yield kind, relation, rows


def describe(row, kind, relation):
    reading = getattr(row, relation)
    entry = reading.daily_entry
    equipment = getattr(reading, kind)
    return {
        'id': row.id, 'type': kind, 'entry_id': entry.id,
        'entry_date': entry.entry_date.isoformat(), 'status': entry.status,
        'equipment': equipment.label, 'product_type': equipment.product_type,
        'uploaded_by': row.uploaded_by.username, 'uploaded_at': row.uploaded_at,
        'url': f'/api/evidence/{kind}/{row.id}/image/',
        'storage': 'cloudinary' if row.image.name.startswith('cloudinary/') else 'legacy',
    }


class AdminMediaView(APIView):
    permission_classes = [IsStationAdmin]

    def get(self, request):
        before = parse_report_date(request.query_params['before'], 'before') if request.query_params.get('before') else None
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except ValueError:
            raise ValidationError('Page must be a number.')
        page_size = 40
        end = page * page_size
        rows = []
        total = 0
        for kind, relation, queryset in media_rows(request.user.station, before):
            total += queryset.count()
            rows.extend(describe(row, kind, relation) for row in queryset.order_by('-uploaded_at', '-id')[:end])
        rows.sort(key=lambda row: (row['uploaded_at'], row['type'], row['id']), reverse=True)
        pending = MediaDeletionJob.objects.filter(station=request.user.station, completed_at__isnull=True).count()
        return Response({'results': rows[end - page_size:end], 'count': total, 'page': page, 'page_size': page_size, 'pending_deletions': pending})


class MediaSelection(serializers.Serializer):
    type = serializers.ChoiceField(choices=['pump', 'tank'])
    id = serializers.IntegerField(min_value=1)


class MediaDeleteInput(serializers.Serializer):
    confirm = serializers.CharField()
    items = MediaSelection(many=True, allow_empty=False, max_length=20)

    def validate_confirm(self, value):
        if value != 'DELETE MEDIA':
            raise serializers.ValidationError('Type DELETE MEDIA to confirm.')
        return value


class AdminMediaDeleteView(APIView):
    permission_classes = [IsStationAdmin]

    def post(self, request):
        serializer = MediaDeleteInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data['items']
        # Validate the entire selection before deleting any file.
        for item in items:
            model, relation = MODELS[item['type']]
            if not model.objects.filter(pk=item['id'], **{relation + '__daily_entry__station': request.user.station}).exists():
                raise Http404('Selected photo not found for this station. Refresh the gallery.')
        deleted, failed = [], []
        seen = set()
        for item in items:
            key = (item['type'], item['id'])
            if key in seen:
                continue
            seen.add(key)
            model, relation = MODELS[item['type']]
            try:
                with transaction.atomic():
                    row = model.objects.select_for_update().filter(pk=item['id'], **{relation + '__daily_entry__station': request.user.station}).first()
                    if row:
                        row.image.storage.delete(row.image.name)
                        row._remote_deleted = True
                        row.delete()
                deleted.append(item)
            except Exception:
                # Keep the database record so the admin can retry the exact asset.
                failed.append({**item, 'error': 'Cloudinary removal was not confirmed. The photo remains listed; retry deletion.'})
        return Response({'deleted': deleted, 'failed': failed})


class AdminMediaRetryView(APIView):
    permission_classes = [IsStationAdmin]

    def post(self, request):
        ids = list(MediaDeletionJob.objects.filter(station=request.user.station, completed_at__isnull=True).values_list('pk', flat=True)[:20])
        completed = sum(process_deletion(pk) for pk in ids)
        pending = MediaDeletionJob.objects.filter(station=request.user.station, completed_at__isnull=True).count()
        return Response({'completed': completed, 'pending': pending})


class AdminMediaExportView(APIView):
    permission_classes = [IsStationAdmin]

    def get(self, request):
        output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        manifest, missing = [], []
        try:
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                for kind, relation, queryset in media_rows(request.user.station):
                    for row in queryset.iterator(chunk_size=100):
                        name = PurePosixPath(row.image.name).name
                        info = describe(row, kind, relation)
                        member = f"{info['entry_date']}/{kind}-{row.id}-{name}"
                        try:
                            with row.image.open('rb') as file:
                                archive.writestr(member, file.read())
                        except FileNotFoundError:
                            missing.append({'type': kind, 'id': row.id})
                            continue
                        info['file'] = member
                        info['uploaded_at'] = info['uploaded_at'].isoformat()
                        manifest.append(info)
                archive.writestr('manifest.json', json.dumps({'station': request.user.station.name, 'exported_at': timezone.now().isoformat(), 'photos': manifest, 'missing_photos': missing}, indent=2))
                archive.writestr('README.txt', 'Station photos grouped by business date. manifest.json links each file to its pump/tank reading and lists any missing originals.\n')
            output.seek(0)
            response = FileResponse(output, as_attachment=True, filename=f'station-media-{timezone.now():%Y%m%d-%H%M%S}.zip', content_type='application/zip')
            response['Cache-Control'] = 'no-store'
            return response
        except Exception:
            output.close()
            raise APIException('Media download could not finish. Please retry; no files were deleted.') from None


class MediaFileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        name = request.query_params.get('name')
        if not name:
            raise Http404()
        for kind, (model, relation) in MODELS.items():
            row = model.objects.filter(image=name, **{relation + '__daily_entry__station': request.user.station_id}).first()
            if row:
                return EvidenceImageView().get(request, kind, row.pk)
        raise Http404()
