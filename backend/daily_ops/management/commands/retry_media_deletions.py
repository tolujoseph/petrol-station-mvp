from django.core.management.base import BaseCommand
from daily_ops.models import MediaDeletionJob
from daily_ops.media import process_deletion


class Command(BaseCommand):
    help = 'Retry persisted storage deletions left by removed entries or drafts.'

    def handle(self, *args, **options):
        ids = list(MediaDeletionJob.objects.filter(completed_at__isnull=True).values_list('pk', flat=True)[:100])
        completed = sum(process_deletion(pk) for pk in ids)
        self.stdout.write(f'Verified {completed}/{len(ids)} pending media deletions.')
