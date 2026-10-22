
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from daily_ops.models import (
    DailyEntry,
    DailyResult,
    FinancialTransaction,
    Pump,
    PumpReading,
    PumpReadingEvidence,
    ReconciliationSettings,
    Station,
    Tank,
    TankReading,
    TankReadingEvidence,
    User,
)


class DraftLifecycleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.station = Station.objects.create(name="Draft Station")
        self.manager = User.objects.create_user(
            username="draft_manager", password="test-password-123",
            station=self.station, role=User.Role.MANAGER,
        )
        self.other_station = Station.objects.create(name="Other Draft Station")
        self.other_manager = User.objects.create_user(
            username="other_draft_manager", password="test-password-123",
            station=self.other_station, role=User.Role.MANAGER,
        )
        self.pump = Pump.objects.create(
            station=self.station, label="Pump 1", product_type=Pump.ProductType.PMS,
        )
        self.tank = Tank.objects.create(
            station=self.station, label="Tank 1", product_type=Tank.ProductType.PMS,
        )
        self.client.force_authenticate(user=self.manager)

    def create_draft(self):
        response = self.client.post("/api/daily-entries/", {
            "entry_date": "2026-10-21",
            "notes": "Initial notes",
            "pump_readings": [{"pump": self.pump.id, "closing_reading": "100.00"}],
            "tank_readings": [{"tank": self.tank.id, "closing_reading": "200.00"}],
            "financial_transactions": [],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        return response.data["id"]

    def test_manager_can_list_and_resume_own_draft(self):
        entry_id = self.create_draft()
        list_response = self.client.get("/api/daily-entries/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([row["id"] for row in list_response.data], [entry_id])

        detail_response = self.client.get(f"/api/daily-entries/{entry_id}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["pump_readings"][0]["closing_reading"], "100.00")
        self.assertEqual(detail_response.data["tank_readings"][0]["closing_reading"], "200.00")

    def test_manager_can_update_existing_draft_without_recreating_readings(self):
        entry_id = self.create_draft()
        reading = PumpReading.objects.get(daily_entry_id=entry_id)
        response = self.client.patch(f"/api/daily-entries/{entry_id}/", {
            "notes": "Updated notes",
            "pump_readings": [{"pump": self.pump.id, "closing_reading": "125.00"}],
            "tank_readings": [{"tank": self.tank.id, "closing_reading": "225.00"}],
            "financial_transactions": [{
                "product_type": "PMS", "transaction_type": "POS",
                "amount": "250.00", "description": "POS takings",
            }],
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["notes"], "Updated notes")
        self.assertEqual(PumpReading.objects.filter(daily_entry_id=entry_id).count(), 1)
        self.assertEqual(PumpReading.objects.get(pk=reading.pk).closing_reading, Decimal("125.00"))
        self.assertEqual(FinancialTransaction.objects.filter(daily_entry_id=entry_id).count(), 1)

    def test_manager_can_discard_draft_only_after_explicit_delete_request(self):
        entry_id = self.create_draft()
        response = self.client.delete(f"/api/daily-entries/{entry_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(DailyEntry.objects.filter(pk=entry_id).exists())

    def test_manager_cannot_access_another_managers_draft(self):
        entry_id = self.create_draft()
        self.client.force_authenticate(user=self.other_manager)
        response = self.client.get(f"/api/daily-entries/{entry_id}/")
        self.assertEqual(response.status_code, 404)
        delete_response = self.client.delete(f"/api/daily-entries/{entry_id}/")
        self.assertEqual(delete_response.status_code, 404)

    def test_submitted_entry_cannot_be_edited_or_discarded(self):
        entry_id = self.create_draft()
        entry = DailyEntry.objects.get(pk=entry_id)
        entry.status = DailyEntry.Status.SUBMITTED
        entry.submitted_at = timezone.now()
        entry.save(update_fields=["status", "submitted_at"])
        patch_response = self.client.patch(f"/api/daily-entries/{entry_id}/", {"notes": "No"}, format="json")
        self.assertEqual(patch_response.status_code, 404)
        delete_response = self.client.delete(f"/api/daily-entries/{entry_id}/")
        self.assertEqual(delete_response.status_code, 400)


class DailyEntryTransactionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.station = Station.objects.create(
            name="Transaction Test Station",
            location="Test Location",
        )
        self.manager = User.objects.create_user(
            username="transaction_manager",
            password="test-password-123",
            station=self.station,
            role=User.Role.MANAGER,
        )
        self.client.force_authenticate(user=self.manager)

        self.pump = Pump.objects.create(
            station=self.station,
            label="Pump 1",
            product_type=Pump.ProductType.PMS,
        )
        self.tank = Tank.objects.create(
            station=self.station,
            label="Tank 1",
            product_type=Tank.ProductType.PMS,
        )

        ReconciliationSettings.objects.create(
            station=self.station,
            adjustment_divisor="20",
            adjustment_factor="0.85",
            physical_tolerance="5",
            effective_from="2026-01-01",
        )

    def test_failed_submission_rolls_back_all_records(self):
        payload = {
            "entry_date": "2026-10-09",
            "pump_readings": [
                {
                    "pump": self.pump.id,
                    "closing_reading": "1100.00",
                }
            ],
            "tank_readings": [
                {
                    "tank": self.tank.id,
                    "closing_reading": "4900.00",
                }
            ],
            "financial_transactions": [
                {
                    "product_type": "PMS",
                    "transaction_type": "POS",
                    "amount": "150000.00",
                    "description": "Test POS sales",
                }
            ],
        }

        draft_response = self.client.post(
            "/api/daily-entries/",
            payload,
            format="json",
        )

        self.assertEqual(draft_response.status_code, 201)

        entry_id = draft_response.data["id"]
        entry = DailyEntry.objects.get(id=entry_id)

        pump_reading = PumpReading.objects.get(daily_entry=entry)
        tank_reading = TankReading.objects.get(daily_entry=entry)

        PumpReadingEvidence.objects.create(
            pump_reading=pump_reading,
            image="test-evidence/pump.jpg",
            uploaded_by=self.manager,
        )
        TankReadingEvidence.objects.create(
            tank_reading=tank_reading,
            image="test-evidence/tank.jpg",
            uploaded_by=self.manager,
        )

        with patch(
            "daily_ops.api.views.simulate_daily_entry",
            side_effect=ValueError("Simulated calculation failure"),
        ):
            response = self.client.post(
                f"/api/daily-entries/{entry_id}/finalise/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 500)

        entry.refresh_from_db()
        self.assertEqual(entry.status, DailyEntry.Status.DRAFT)
        self.assertIsNone(entry.submitted_at)

        self.assertEqual(DailyEntry.objects.count(), 1)
        self.assertEqual(PumpReading.objects.count(), 1)
        self.assertEqual(TankReading.objects.count(), 1)
        self.assertEqual(FinancialTransaction.objects.count(), 1)
        self.assertEqual(DailyResult.objects.count(), 0)


class StationDataIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.station_a = Station.objects.create(
            name="Station A",
            location="Leeds",
        )
        self.station_b = Station.objects.create(
            name="Station B",
            location="Bradford",
        )

        self.owner_a = User.objects.create_user(
            username="owner_a",
            password="test-password-123",
            station=self.station_a,
            role=User.Role.OWNER,
        )
        self.owner_b = User.objects.create_user(
            username="owner_b",
            password="test-password-123",
            station=self.station_b,
            role=User.Role.OWNER,
        )

        self.result_a = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-10-08",
        )
        self.result_b = self.create_daily_result(
            station=self.station_b,
            manager=self.owner_b,
            entry_date="2026-10-08",
        )

    def create_daily_result(
        self,
        station,
        manager,
        entry_date,
        **result_overrides,
    ):
        entry = DailyEntry.objects.create(
            station=station,
            manager=manager,
            entry_date=entry_date,
            status=DailyEntry.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )

        result_values = {
            "pump_volume": "100.00",
            "tank_movement": "95.00",
            "physical_difference": "5.00",
            "expected_revenue": "150.00",
            "actual_sales": "140.00",
            "financial_difference": "10.00",
            "fuel_cost": "95.00",
            "gross_profit": "55.00",
            "expenses": "5.00",
            "net_profit": "50.00",
        }
        result_values.update(result_overrides)

        return DailyResult.objects.create(
            daily_entry=entry,
            **result_values,
        )

    def authenticate_station_a(self):
        self.client.force_authenticate(user=self.owner_a)

    def test_owner_can_create_effective_dated_reconciliation_settings(self):
        self.authenticate_station_a()
        response = self.client.post(
            "/api/station/settings/reconciliation/",
            {
                "adjustment_divisor": "20",
                "adjustment_factor": "0.85",
                "physical_tolerance": "5.00",
                "adjustment_tolerance": "0.05",
                "effective_from": "2026-11-01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["physical_tolerance"], "5.0000")
        self.assertEqual(response.data["adjustment_tolerance"], "0.0500")
        self.assertEqual(
            ReconciliationSettings.objects.filter(station=self.station_a).count(),
            1,
        )

    def test_manager_can_read_but_cannot_create_station_settings(self):
        manager = User.objects.create_user(
            username="settings_manager",
            password="test-password-123",
            station=self.station_a,
            role=User.Role.MANAGER,
        )
        ReconciliationSettings.objects.create(
            station=self.station_a,
            adjustment_divisor="20",
            adjustment_factor="0.85",
            physical_tolerance="5",
            adjustment_tolerance="0.05",
            effective_from="2026-01-01",
        )
        self.client.force_authenticate(user=manager)

        read_response = self.client.get("/api/station/settings/reconciliation/")
        write_response = self.client.post(
            "/api/station/settings/reconciliation/",
            {
                "adjustment_divisor": "20",
                "adjustment_factor": "0.85",
                "physical_tolerance": "5",
                "adjustment_tolerance": "0.05",
                "effective_from": "2026-11-01",
            },
            format="json",
        )

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(len(read_response.data), 1)
        self.assertEqual(write_response.status_code, 404)
        self.assertEqual(ReconciliationSettings.objects.filter(station=self.station_a).count(), 1)

    def test_daily_results_only_include_users_station(self):
        self.authenticate_station_a()

        response = self.client.get("/api/reports/daily-results/")

        self.assertEqual(response.status_code, 200)
        returned_ids = [item["id"] for item in response.data]
        self.assertEqual(returned_ids, [self.result_a.id])

    def test_discrepancy_report_only_includes_owners_station(self):
        self.authenticate_station_a()

        response = self.client.get("/api/reports/discrepancies/")

        self.assertEqual(response.status_code, 200)
        returned_ids = [item["id"] for item in response.data]
        self.assertEqual(returned_ids, [self.result_a.id])

    def test_latest_official_submission_is_returned(self):
        self.authenticate_station_a()

        older_result = self.result_a
        older_result.daily_entry.submitted_at = timezone.now() - timedelta(
            days=2
        )
        older_result.daily_entry.save(update_fields=["submitted_at"])

        newer_result = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-10-08",
            actual_sales="250.00",
        )

        response = self.client.get("/api/reports/daily-results/")

        self.assertEqual(response.status_code, 200)
        returned_ids = [item["id"] for item in response.data]
        self.assertEqual(returned_ids, [newer_result.id])

    def test_newer_draft_does_not_replace_official_submission(self):
        self.authenticate_station_a()

        draft = DailyEntry.objects.create(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-10-08",
            status=DailyEntry.Status.DRAFT,
        )

        response = self.client.get("/api/reports/daily-results/")

        self.assertEqual(response.status_code, 200)
        returned_ids = [item["id"] for item in response.data]
        self.assertEqual(returned_ids, [self.result_a.id])
        self.assertFalse(
            DailyResult.objects.filter(daily_entry=draft).exists()
        )

    def test_old_submission_and_result_remain_stored(self):
        self.authenticate_station_a()

        old_result = self.result_a
        old_entry = old_result.daily_entry

        old_entry.submitted_at = timezone.now() - timedelta(days=2)
        old_entry.save(update_fields=["submitted_at"])

        newer_result = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-10-08",
            actual_sales="250.00",
        )

        self.assertTrue(
            DailyEntry.objects.filter(id=old_entry.id).exists()
        )
        self.assertTrue(
            DailyResult.objects.filter(id=old_result.id).exists()
        )
        self.assertTrue(
            DailyResult.objects.filter(id=newer_result.id).exists()
        )

    def test_inclusive_date_range_filters_daily_results(self):
        self.authenticate_station_a()

        # Use November so the baseline result from 8 October is excluded.
        inside_start = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-10",
        )
        inside_end = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-20",
        )
        self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-21",
        )

        response = self.client.get(
            "/api/reports/daily-results/",
            {
                "start_date": "2026-11-10",
                "end_date": "2026-11-20",
            },
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {item["id"] for item in response.data}
        self.assertEqual(
            returned_ids,
            {inside_start.id, inside_end.id},
        )

    def test_start_date_only_filters_daily_results(self):
        self.authenticate_station_a()

        included = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-10",
        )
        excluded = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-09",
        )

        response = self.client.get(
            "/api/reports/daily-results/",
            {"start_date": "2026-11-10"},
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {item["id"] for item in response.data}
        self.assertIn(included.id, returned_ids)
        self.assertNotIn(excluded.id, returned_ids)
        self.assertNotIn(self.result_a.id, returned_ids)

    def test_end_date_only_filters_daily_results(self):
        self.authenticate_station_a()

        included = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-10",
        )
        excluded = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-11",
        )

        response = self.client.get(
            "/api/reports/daily-results/",
            {"end_date": "2026-11-10"},
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = {item["id"] for item in response.data}
        self.assertIn(included.id, returned_ids)
        self.assertNotIn(excluded.id, returned_ids)

    def test_discrepancy_report_respects_date_range(self):
        self.authenticate_station_a()

        included = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-10",
        )
        self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-21",
        )

        response = self.client.get(
            "/api/reports/discrepancies/",
            {
                "start_date": "2026-11-10",
                "end_date": "2026-11-10",
            },
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = [item["id"] for item in response.data]
        self.assertEqual(returned_ids, [included.id])

    def test_invalid_report_dates_return_400(self):
        self.authenticate_station_a()

        invalid_queries = [
            {"date": "2026-02-30"},
            {"start_date": "not-a-date"},
            {"end_date": "2026-02-30"},
        ]

        for query_params in invalid_queries:
            with self.subTest(query_params=query_params):
                response = self.client.get(
                    "/api/reports/daily-results/",
                    query_params,
                )
                self.assertEqual(response.status_code, 400)

    def test_reversed_date_range_returns_400(self):
        self.authenticate_station_a()

        response = self.client.get(
            "/api/reports/daily-results/",
            {
                "start_date": "2026-11-20",
                "end_date": "2026-11-10",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_exact_date_cannot_be_combined_with_range(self):
        self.authenticate_station_a()

        response = self.client.get(
            "/api/reports/daily-results/",
            {
                "date": "2026-11-10",
                "start_date": "2026-11-01",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_monthly_grouping_aggregates_results(self):
        self.authenticate_station_a()

        self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-10-15",
        )
        self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-10-20",
        )

        response = self.client.get(
            "/api/reports/daily-results/",
            {"group_by": "month"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["group_by"], "month")

        october = next(
            item
            for item in response.data["results"]
            if item["period"] == "2026-10"
        )

        self.assertEqual(october["entry_count"], 3)
        self.assertEqual(october["pump_volume"], "300.00")
        self.assertEqual(october["actual_sales"], "420.00")
        self.assertEqual(october["expenses"], "15.00")
        self.assertEqual(october["net_profit"], "150.00")

    def test_yearly_grouping_separates_years(self):
        self.authenticate_station_a()

        self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2025-12-31",
        )
        self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-01-01",
        )

        response = self.client.get(
            "/api/reports/daily-results/",
            {"group_by": "year"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["group_by"], "year")

        periods = {
            item["period"]: item
            for item in response.data["results"]
        }

        self.assertIn("2025", periods)
        self.assertIn("2026", periods)
        self.assertEqual(periods["2025"]["entry_count"], 1)
        self.assertEqual(periods["2026"]["entry_count"], 2)

    def test_daily_grouping_returns_one_summary_per_date(self):
        self.authenticate_station_a()

        self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-10-14",
        )
        self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-10-15",
        )

        response = self.client.get(
            "/api/reports/daily-results/",
            {"group_by": "day"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["group_by"], "day")

        periods = {
            item["period"]
            for item in response.data["results"]
        }
        self.assertEqual(
            periods,
            {"2026-10-08", "2026-10-14", "2026-10-15"},
        )

    def test_invalid_group_by_returns_400(self):
        self.authenticate_station_a()

        response = self.client.get(
            "/api/reports/daily-results/",
            {"group_by": "week"},
        )

        self.assertEqual(response.status_code, 400)

    def test_aggregation_respects_date_range(self):
        self.authenticate_station_a()

        included = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-10",
        )
        self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-11-11",
        )

        response = self.client.get(
            "/api/reports/daily-results/",
            {
                "group_by": "month",
                "start_date": "2026-11-10",
                "end_date": "2026-11-10",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

        summary = response.data["results"][0]
        self.assertEqual(summary["period"], "2026-11")
        self.assertEqual(summary["entry_count"], 1)
        self.assertEqual(summary["pump_volume"], "100.00")

    def test_aggregation_only_uses_latest_official_submission(self):
        self.authenticate_station_a()

        older_entry = self.result_a.daily_entry
        older_entry.submitted_at = timezone.now() - timedelta(days=2)
        older_entry.save(update_fields=["submitted_at"])

        newer_result = self.create_daily_result(
            station=self.station_a,
            manager=self.owner_a,
            entry_date="2026-10-08",
            pump_volume="200.00",
            actual_sales="250.00",
        )

        response = self.client.get(
            "/api/reports/daily-results/",
            {
                "group_by": "month",
                "start_date": "2026-10-08",
                "end_date": "2026-10-08",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

        summary = response.data["results"][0]
        self.assertEqual(summary["entry_count"], 1)
        self.assertEqual(summary["pump_volume"], "200.00")
        self.assertEqual(summary["actual_sales"], "250.00")

class AdditionalSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.station = Station.objects.create(
            name="Security Test Station",
            location="Leeds",
        )
        self.other_station = Station.objects.create(
            name="Other Station",
            location="Bradford",
        )

        self.manager = User.objects.create_user(
            username="security_manager",
            password="test-password-123",
            station=self.station,
            role=User.Role.MANAGER,
        )
        self.unassigned_manager = User.objects.create_user(
            username="unassigned_manager",
            password="test-password-123",
            station=None,
            role=User.Role.MANAGER,
        )

        self.own_pump = Pump.objects.create(
            station=self.station,
            label="Own Pump",
            product_type=Pump.ProductType.PMS,
        )
        self.own_tank = Tank.objects.create(
            station=self.station,
            label="Own Tank",
            product_type=Tank.ProductType.PMS,
        )
        self.other_pump = Pump.objects.create(
            station=self.other_station,
            label="Other Pump",
            product_type=Pump.ProductType.PMS,
        )
        self.other_tank = Tank.objects.create(
            station=self.other_station,
            label="Other Tank",
            product_type=Tank.ProductType.PMS,
        )

    def test_unassigned_manager_cannot_submit_daily_entry(self):
        self.client.force_authenticate(user=self.unassigned_manager)

        response = self.client.post(
            "/api/daily-entries/",
            {
                "entry_date": "2026-10-09",
                "pump_readings": [],
                "tank_readings": [],
                "financial_transactions": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(DailyEntry.objects.count(), 0)

    def test_manager_cannot_submit_another_stations_pump(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            "/api/daily-entries/",
            {
                "entry_date": "2026-10-09",
                "pump_readings": [
                    {
                        "pump": self.other_pump.id,
                        "closing_reading": "100.00",
                    }
                ],
                "tank_readings": [
                    {
                        "tank": self.own_tank.id,
                        "closing_reading": "1000.00",
                    }
                ],
                "financial_transactions": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(DailyEntry.objects.count(), 0)

    def test_manager_cannot_submit_another_stations_tank(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.post(
            "/api/daily-entries/",
            {
                "entry_date": "2026-10-09",
                "pump_readings": [
                    {
                        "pump": self.own_pump.id,
                        "closing_reading": "100.00",
                    }
                ],
                "tank_readings": [
                    {
                        "tank": self.other_tank.id,
                        "closing_reading": "1000.00",
                    }
                ],
                "financial_transactions": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(DailyEntry.objects.count(), 0)
