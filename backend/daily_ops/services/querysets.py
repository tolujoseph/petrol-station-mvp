from django.db.models import F, OuterRef, Subquery

from ..models import DailyEntry


def official_daily_entry_ids(station):
    """IDs of the latest successfully submitted entry for each station date."""
    latest_entry = DailyEntry.objects.filter(
        station_id=OuterRef("station_id"),
        entry_date=OuterRef("entry_date"),
        status=DailyEntry.Status.SUBMITTED,
        submitted_at__isnull=False,
    ).order_by("-submitted_at", "-id")

    return DailyEntry.objects.filter(
        station=station,
        status=DailyEntry.Status.SUBMITTED,
        submitted_at__isnull=False,
    ).annotate(
        latest_entry_id=Subquery(latest_entry.values("id")[:1])
    ).filter(
        id=F("latest_entry_id")
    ).values_list("id", flat=True)
