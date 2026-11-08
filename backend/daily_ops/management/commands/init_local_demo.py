"""Initialize only an empty, local Compose database; never reset saved accounts."""
import os

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction

from daily_ops.models import Station, User


class Command(BaseCommand):
    help = 'Create demo logins and equipment once in the local Docker database.'

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        if (os.environ.get('K_SERVICE') or not settings.DEBUG
                or db.get('HOST') != 'db' or db.get('NAME') != 'petrol_local'):
            raise CommandError('Local demo initialization requires the local Docker database.')
        with transaction.atomic():
            if Station.objects.exists() or User.objects.exists():
                self.stdout.write('Local database already initialized; keeping existing data and passwords.')
                return
            call_command('seed_demo', days=0, stdout=self.stdout)
