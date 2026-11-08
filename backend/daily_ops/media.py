from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from .models import MediaDeletionJob


def process_deletion(job_id):
    job = MediaDeletionJob.objects.filter(pk=job_id, completed_at__isnull=True).first()
    if not job:
        return True
    try:
        default_storage.delete(job.name)
    except Exception:
        job.attempts += 1
        job.last_error = 'Storage removal failed. Retry to verify the file is deleted.'
        job.save(update_fields=['attempts', 'last_error'])
        return False
    job.attempts += 1
    job.completed_at = timezone.now()
    job.last_error = ''
    job.save(update_fields=['attempts', 'completed_at', 'last_error'])
    return True


def queue_deletion(name, station_id):
    job, _ = MediaDeletionJob.objects.get_or_create(name=name, defaults={'station_id': station_id})
    transaction.on_commit(lambda: process_deletion(job.pk), robust=True)
    return job
