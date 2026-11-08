from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import PumpReadingEvidence, TankReadingEvidence, Station
from .media import queue_deletion


@receiver(post_delete, sender=PumpReadingEvidence)
@receiver(post_delete, sender=TankReadingEvidence)
def delete_evidence_file(sender, instance, **kwargs):
    if not instance.image.name or getattr(instance, '_remote_deleted', False):
        return
    reading = instance.pump_reading if sender is PumpReadingEvidence else instance.tank_reading
    origin = kwargs.get('origin')
    station_deleted = isinstance(origin, Station) or getattr(origin, 'model', None) is Station
    queue_deletion(instance.image.name, None if station_deleted else reading.daily_entry.station_id)
