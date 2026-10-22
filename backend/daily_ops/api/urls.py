
from django.urls import path

from .views import (
    CsrfTokenView,
    CurrentUserView,
    DailyEntryCreateView,
    DailyEntryDetailView,
    DailyResultListView,
    DiscrepancyReportView,
    EvidenceImageView,
    FinaliseDailyEntryView,
    PumpEvidenceUploadView,
    StationEquipmentView,
    StationProductSettingsView,
    StationReconciliationSettingsView,
    TankEvidenceUploadView,
)

urlpatterns = [
    # Authentication and CSRF
    path(
        "auth/me/",
        CurrentUserView.as_view(),
        name="current-user",
    ),
    path(
        "auth/csrf/",
        CsrfTokenView.as_view(),
        name="csrf-token",
    ),

    # Station equipment
    path(
        "station/equipment/",
        StationEquipmentView.as_view(),
        name="station-equipment",
    ),

    # Effective-dated station settings (owner writes, manager reads)
    path(
        "station/settings/products/",
        StationProductSettingsView.as_view(),
        name="station-product-settings",
    ),
    path(
        "station/settings/reconciliation/",
        StationReconciliationSettingsView.as_view(),
        name="station-reconciliation-settings",
    ),

    # Draft creation and finalisation
    path(
        "daily-entries/",
        DailyEntryCreateView.as_view(),
        name="daily-entry-create",
    ),
    path(
        "daily-entries/<int:entry_id>/",
        DailyEntryDetailView.as_view(),
        name="daily-entry-detail",
    ),
    path(
        "daily-entries/<int:entry_id>/finalise/",
        FinaliseDailyEntryView.as_view(),
        name="daily-entry-finalise",
    ),

    # Reading evidence uploads
    path(
        "readings/pumps/<int:reading_id>/evidence/",
        PumpEvidenceUploadView.as_view(),
        name="pump-evidence-upload",
    ),
    path(
        "readings/tanks/<int:reading_id>/evidence/",
        TankEvidenceUploadView.as_view(),
        name="tank-evidence-upload",
    ),
    path(
        "evidence/<str:evidence_type>/<int:evidence_id>/image/",
        EvidenceImageView.as_view(),
        name="evidence-image",
    ),

    # Reports
    path(
        "reports/daily-results/",
        DailyResultListView.as_view(),
        name="daily-results",
    ),
    path(
        "reports/discrepancies/",
        DiscrepancyReportView.as_view(),
        name="discrepancies",
    ),
]
