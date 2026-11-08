import io
import json
import tempfile
import zipfile
from unittest.mock import patch

import cloudinary.api
from django.core.files.base import ContentFile
from django.test import TestCase, SimpleTestCase, override_settings
from rest_framework.test import APIClient
from daily_ops.models import Station, User, Pump, Tank, DailyEntry, PumpReading, TankReading, PumpReadingEvidence, TankReadingEvidence, MediaDeletionJob
from daily_ops.storage import CloudinaryEvidenceStorage


@override_settings(CLOUDINARY_URL='cloudinary://test-key:test-secret@test-cloud')
class CloudinaryStorageTests(SimpleTestCase):
    name = 'cloudinary/petrol-station/' + 'a' * 32 + '.png'

    @patch('cloudinary.uploader.upload')
    def test_upload_is_private_and_not_backed_up(self, upload):
        upload.return_value = {'format': 'png'}
        name = CloudinaryEvidenceStorage()._save('test.png', ContentFile(b'test', name='test.png'))
        self.assertTrue(name.startswith('cloudinary/petrol-station/'))
        self.assertNotIn('test-secret', name)
        self.assertEqual(upload.call_args.kwargs['type'], 'authenticated')
        self.assertFalse(upload.call_args.kwargs['backup'])
        self.assertFalse(upload.call_args.kwargs['overwrite'])

    @patch('cloudinary.api.resource', side_effect=cloudinary.api.NotFound('missing'))
    @patch('cloudinary.uploader.destroy', return_value={'result': 'ok'})
    def test_deletion_invalidates_and_verifies_origin(self, destroy, resource):
        CloudinaryEvidenceStorage().delete(self.name)
        self.assertTrue(destroy.call_args.kwargs['invalidate'])
        self.assertEqual(destroy.call_args.kwargs['type'], 'authenticated')
        resource.assert_called_once()

    @patch('cloudinary.api.resource', return_value={'public_id': 'still-exists'})
    @patch('cloudinary.uploader.destroy', return_value={'result': 'ok'})
    def test_deletion_cannot_claim_success_while_asset_exists(self, destroy, resource):
        with self.assertRaises(OSError): CloudinaryEvidenceStorage().delete(self.name)

    def test_foreign_cloudinary_paths_cannot_be_deleted(self):
        with self.assertRaises(ValueError): CloudinaryEvidenceStorage().delete('cloudinary/some-other-app/photo.png')


class AdminMediaTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.temp.name)
        self.override.enable(); self.addCleanup(self.override.disable)
        self.station = Station.objects.create(name='Media station')
        self.manager = User.objects.create_user('media-manager', role='manager', station=self.station)
        self.owner = User.objects.create_user('media-owner', role='owner', station=self.station)
        self.admin = User.objects.create_user('media-admin', role='owner', is_staff=True, station=self.station)
        self.pump = Pump.objects.create(station=self.station, label='P1', product_type='PMS')
        self.tank = Tank.objects.create(station=self.station, label='T1', product_type='PMS')
        self.entry = DailyEntry.objects.create(station=self.station, manager=self.manager, entry_date='2026-11-07')
        reading = PumpReading.objects.create(daily_entry=self.entry, pump=self.pump, closing_reading=100)
        tankreading = TankReading.objects.create(daily_entry=self.entry, tank=self.tank, closing_reading=100)
        self.photo = PumpReadingEvidence.objects.create(pump_reading=reading, uploaded_by=self.manager, image=ContentFile(b'pump-photo',name='pump.jpg'))
        self.tankphoto = TankReadingEvidence.objects.create(tank_reading=tankreading, uploaded_by=self.manager, image=ContentFile(b'tank-photo',name='tank.jpg'))
        self.client = APIClient(); self.client.force_authenticate(self.admin)

    def body(self):
        return {'confirm': 'DELETE MEDIA', 'items': [{'type': 'pump', 'id': self.photo.id}]}

    def test_admin_can_preview_drafts_and_download_all_media(self):
        response = self.client.get('/api/admin/media/')
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(self.client.get('/api/admin/media/?before=2026-11-06').data['count'], 0)
        response = self.client.get(f'/api/evidence/pump/{self.photo.id}/image/')
        self.assertEqual(b''.join(response.streaming_content), b'pump-photo')
        response = self.client.get('/api/admin/media/export/')
        archive = zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))
        manifest = json.loads(archive.read('manifest.json'))
        self.assertEqual(len(manifest['photos']), 2)
        self.assertEqual(manifest['missing_photos'], [])
        self.assertIn(b'pump-photo', [archive.read(name) for name in archive.namelist()])

    def test_non_admin_cannot_manage_media_and_owner_cannot_read_drafts(self):
        for user in (self.owner, self.manager):
            self.client.force_authenticate(user)
            for path in ('/api/admin/media/', '/api/admin/media/export/'):
                self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.post('/api/admin/media/delete/', self.body(), format='json').status_code, 403)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(f'/api/evidence/pump/{self.photo.id}/image/').status_code, 404)

    def test_cross_station_selection_is_rejected_before_any_deletion(self):
        other = Station.objects.create(name='Other')
        self.client.force_authenticate(User.objects.create_user('other-admin', station=other, is_staff=True))
        self.assertEqual(self.client.get('/api/admin/media/').data['count'], 0)
        self.assertEqual(self.client.post('/api/admin/media/delete/', self.body(), format='json').status_code, 404)
        self.assertTrue(self.photo.image.storage.exists(self.photo.image.name))

    def test_delete_removes_file_but_keeps_daily_readings(self):
        name = self.photo.image.name
        response = self.client.post('/api/admin/media/delete/', self.body(), format='json')
        self.assertEqual(len(response.data['deleted']), 1)
        self.assertFalse(response.data['failed'])
        self.assertFalse(PumpReadingEvidence.objects.filter(pk=self.photo.pk).exists())
        self.assertFalse(self.photo.image.storage.exists(name))
        self.assertTrue(DailyEntry.objects.filter(pk=self.entry.pk).exists())
        self.assertEqual(self.entry.pump_readings.count(), 1)

    def test_failed_storage_delete_keeps_record_for_retry(self):
        with patch('django.core.files.storage.filesystem.FileSystemStorage.delete', side_effect=OSError('unavailable')):
            response = self.client.post('/api/admin/media/delete/', self.body(), format='json')
        self.assertFalse(response.data['deleted'])
        self.assertEqual(len(response.data['failed']), 1)
        self.assertTrue(PumpReadingEvidence.objects.filter(pk=self.photo.pk).exists())

    def test_delete_requires_explicit_confirmation(self):
        body = self.body(); body['confirm'] = 'no'
        self.assertEqual(self.client.post('/api/admin/media/delete/', body, format='json').status_code, 400)
        self.assertTrue(PumpReadingEvidence.objects.filter(pk=self.photo.pk).exists())

    def test_cascade_failure_is_durable_and_admin_can_retry(self):
        name = self.photo.image.name
        with patch('django.core.files.storage.filesystem.FileSystemStorage.delete', side_effect=OSError('unavailable')):
            with self.captureOnCommitCallbacks(execute=True): self.entry.delete()
        job = MediaDeletionJob.objects.get(name=name)
        self.assertIsNone(job.completed_at)
        self.assertEqual(job.attempts, 1)
        self.assertEqual(self.client.get('/api/admin/media/').data['pending_deletions'], 2)
        response = self.client.post('/api/admin/media/retry/', {}, format='json')
        self.assertEqual(response.data['pending'], 0)
        self.assertFalse(self.photo.image.storage.exists(name))

    def test_missing_photo_is_reported_in_media_zip(self):
        self.photo.image.storage.delete(self.photo.image.name)
        response = self.client.get('/api/admin/media/export/')
        archive = zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))
        manifest = json.loads(archive.read('manifest.json'))
        self.assertEqual(manifest['missing_photos'], [{'type': 'pump', 'id': self.photo.id}])
