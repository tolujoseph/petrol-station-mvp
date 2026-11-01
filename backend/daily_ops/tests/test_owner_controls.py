import io
import json
import tempfile
import zipfile
from datetime import date
from decimal import Decimal

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from daily_ops.columns import seed_columns
from daily_ops.models import (DailyEntry, DailyResult, EntryEdit, FinancialTransaction, ProductSettings, Pump,
    PumpReading, PumpReadingEvidence, ReconciliationSettings, Station, Tank, TankReading, TransactionColumn, User)
from daily_ops.services.orchestration import save_daily_result, simulate_daily_entry


class OwnerControlsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.station = Station.objects.create(name='Test station')
        self.other = Station.objects.create(name='Other station')
        self.manager = User.objects.create_user('manager', station=self.station, role='manager')
        self.owner = User.objects.create_user('owner', station=self.station, role='owner')
        self.admin = User.objects.create_user('admin', station=self.station, role='owner', is_staff=True)
        self.stranger = User.objects.create_user('other', station=self.other, role='owner')
        self.pump = Pump.objects.create(station=self.station, label='P1', product_type='PMS')
        self.tank = Tank.objects.create(station=self.station, label='T1', product_type='PMS')
        ProductSettings.objects.create(station=self.station, product_type='PMS', selling_price=100, landing_cost=80, effective_from=date(2026, 1, 1))
        ReconciliationSettings.objects.create(station=self.station, adjustment_divisor=20, adjustment_factor=0, physical_tolerance=5, effective_from=date(2026, 1, 1))
        seed_columns(self.station)
        self.column = self.station.transaction_columns.get(label='Wema POS')
        self.entries = []
        for day, meter, dip in [(1, 100, 1000), (2, 200, 900), (3, 300, 800)]:
            entry = DailyEntry.objects.create(station=self.station, manager=self.manager, entry_date=date(2026, 10, day), status='submitted', submitted_at=timezone.now())
            PumpReading.objects.create(daily_entry=entry, pump=self.pump, closing_reading=meter)
            TankReading.objects.create(daily_entry=entry, tank=self.tank, closing_reading=dip)
            FinancialTransaction.objects.create(daily_entry=entry, product_type='PMS', transaction_type='POS', column=self.column, amount=10000)
            save_daily_result(entry, simulate_daily_entry(entry))
            self.entries.append(entry)
        self.client.force_authenticate(self.owner)

    def test_columns_create_hide_restore_and_keep_old_transactions(self):
        self.assertEqual(self.client.get('/api/station/columns/').status_code, 200)
        self.assertEqual(self.station.transaction_columns.count(), 10)
        response = self.client.post('/api/station/columns/', {'label': 'Cash collected', 'transaction_type': 'cash_bank'}, format='json')
        self.assertEqual(response.status_code, 201)
        path = f'/api/station/columns/{self.column.id}/'
        self.assertEqual(self.client.patch(path, {'active': False}, format='json').status_code, 200)
        self.assertEqual(FinancialTransaction.objects.filter(column=self.column).count(), 3)
        self.assertEqual(self.client.delete(path).status_code, 405)
        self.assertEqual(self.client.patch(path, {'active': True}, format='json').status_code, 200)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.patch(path, {'active': False}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/station/columns/', {'label': 'No'}, format='json').status_code, 403)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.patch(path, {'active': False}, format='json').status_code, 404)

    def test_equipment_add_hide_restore_no_delete(self):
        created = self.client.post('/api/station/settings/equipment/', {'kind': 'pump', 'label': 'P2', 'product_type': 'AGO'}, format='json')
        self.assertEqual(created.status_code, 201)
        path = f'/api/station/settings/equipment/pump/{self.pump.id}/'
        self.assertEqual(self.client.patch(path, {'active': False}, format='json').status_code, 200)
        self.assertEqual(len(self.client.get('/api/station/equipment/').data['pumps']), 1)
        self.assertEqual(PumpReading.objects.filter(pump=self.pump).count(), 3)
        self.assertEqual(self.client.delete(path).status_code, 405)
        self.assertEqual(self.client.patch(path, {'active': True}, format='json').status_code, 200)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get('/api/station/settings/equipment/').status_code, 403)

    def test_owner_edit_recalculates_following_days_and_records_actor(self):
        entry = self.entries[1]
        response = self.client.patch(f'/api/saved-entries/{entry.id}/', {'version': 0, 'pump_readings': [{'pump': self.pump.id, 'closing_reading': '220.00'}], 'notes': 'Corrected meter'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(DailyResult.objects.get(daily_entry=entry).pump_volume, Decimal('120'))
        self.assertEqual(DailyResult.objects.get(daily_entry=self.entries[2]).pump_volume, Decimal('80'))
        edit = EntryEdit.objects.get(entry=entry)
        self.assertEqual(edit.edited_by, self.owner)
        self.assertEqual(edit.before['pump_readings'][0]['closing_reading'], '200.00')
        self.assertEqual(response.data['version'], 1)
        self.assertEqual(self.client.patch(f'/api/saved-entries/{entry.id}/', {'version': 0, 'notes': 'Stale change'}, format='json').status_code, 409)
        entry.refresh_from_db()
        self.assertEqual(entry.manager, self.manager)

    def test_failed_recalculation_rolls_back_all_changes(self):
        entry = self.entries[1]
        ProductSettings.objects.all().delete()
        response = self.client.patch(f'/api/saved-entries/{entry.id}/', {'version': 0, 'notes': 'Must roll back'}, format='json')
        self.assertEqual(response.status_code, 400)
        entry.refresh_from_db()
        self.assertEqual(entry.notes, '')
        self.assertFalse(EntryEdit.objects.exists())

    def test_manager_history_date_and_entry_permissions(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get('/api/reports/daily-results/?date=2026-10-02')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['daily_entry'], self.entries[1].id)
        response = self.client.get('/api/saved-entries/?date=2026-10-02')
        self.assertEqual(response.data['pump_readings'][0]['closing_reading'], '200.00')
        self.assertEqual(self.client.patch(f'/api/saved-entries/{self.entries[1].id}/', {'version': 0, 'notes': 'No'}, format='json').status_code, 403)
        other_manager = User.objects.create_user('colleague', station=self.station, role='manager')
        self.client.force_authenticate(other_manager)
        self.assertEqual(self.client.get(f'/api/saved-entries/{self.entries[1].id}/').status_code, 404)
        self.assertEqual(self.client.get('/api/reports/daily-results/?date=2026-10-02').data, [])
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(f'/api/saved-entries/{self.entries[1].id}/').status_code, 404)

    def test_equipment_openings_respect_selected_date(self):
        response = self.client.get('/api/station/equipment/?before=2026-10-03')
        self.assertEqual(response.data['pumps'][0]['last_reading']['closing_reading'], '200.00')

    def test_hidden_existing_column_can_be_corrected_but_not_newly_used(self):
        self.column.active = False; self.column.save()
        entry = self.entries[1]
        tx = {'column': self.column.id, 'transaction_type': 'expense', 'product_type': 'PMS', 'amount': '12000.00'}
        response = self.client.patch(f'/api/saved-entries/{entry.id}/', {'version': 0, 'financial_transactions': [tx]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(entry.financial_transactions.get().transaction_type, 'POS')
        self.client.force_authenticate(self.manager)
        response = self.client.post('/api/daily-entries/', {'entry_date': '2026-10-04', 'pump_readings': [{'pump': self.pump.id, 'closing_reading': '400'}], 'tank_readings': [{'tank': self.tank.id, 'closing_reading': '700'}], 'financial_transactions': [tx]}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_export_is_admin_only_complete_and_station_scoped(self):
        self.assertEqual(self.client.get('/api/admin/export/').status_code, 403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get('/api/admin/export/').status_code, 403)
        self.client.force_authenticate(self.admin)
        Pump.objects.create(station=self.other, label='Private other pump', product_type='PMS')
        self.column.active = False; self.column.save()
        self.entries[0].notes = '=HYPERLINK("bad")'; self.entries[0].save()
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            photo = PumpReadingEvidence.objects.create(pump_reading=self.entries[0].pump_readings.get(), image=ContentFile(b'photo-content', name='test.jpg'), uploaded_by=self.manager)
            response = self.client.get('/api/admin/export/')
            self.assertEqual(response.status_code, 200)
            archive = zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))
            self.assertEqual(archive.read('media/' + photo.image.name), b'photo-content')
            data = json.loads(archive.read('data.json'))
            self.assertEqual(sum(r['model'] == 'daily_ops.dailyentry' for r in data), 3)
            self.assertNotIn(b'Private other pump', archive.read('data.json'))
            self.assertNotIn(b'password', archive.read('users.json'))
            self.assertIn(b"'=HYPERLINK", archive.read('entries.csv'))
            self.assertEqual(json.loads(archive.read('manifest.json'))['missing_photos'], [])
