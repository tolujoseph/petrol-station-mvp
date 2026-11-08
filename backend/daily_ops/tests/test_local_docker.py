from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase
from daily_ops.models import Station, User

MODULE = 'daily_ops.management.commands.init_local_demo'


class LocalDockerInitializationTests(TestCase):
    def config(self, **changes):
        config = SimpleNamespace(DEBUG=True, DATABASES={'default': {'HOST': 'db', 'NAME': 'petrol_local'}})
        for key, value in changes.items():
            setattr(config, key, value)
        return patch(MODULE + '.settings', config)

    def test_empty_local_database_is_seeded(self):
        with self.config(), patch(MODULE + '.call_command') as seed:
            call_command('init_local_demo', stdout=StringIO())
        seed.assert_called_once()
        self.assertEqual(seed.call_args.args, ('seed_demo',))
        self.assertEqual(seed.call_args.kwargs['days'], 0)

    def test_existing_accounts_and_passwords_are_untouched(self):
        user = User.objects.create_user('keep-me', password='my-changed-password')
        with self.config(), patch(MODULE + '.call_command') as seed:
            call_command('init_local_demo', stdout=StringIO())
        seed.assert_not_called()
        user.refresh_from_db()
        self.assertTrue(user.check_password('my-changed-password'))

    def test_existing_station_is_not_seeded_again(self):
        Station.objects.create(name='Existing')
        with self.config(), patch(MODULE + '.call_command') as seed:
            call_command('init_local_demo', stdout=StringIO())
        seed.assert_not_called()

    def test_production_or_external_database_is_rejected(self):
        for changes in ({'DEBUG': False}, {'DATABASES': {'default': {'HOST': 'remote', 'NAME': 'petrol_local'}}}):
            with self.config(**changes), self.assertRaises(CommandError):
                call_command('init_local_demo', stdout=StringIO())
        with self.config(), patch.dict('os.environ', {'K_SERVICE': 'production'}), self.assertRaises(CommandError):
            call_command('init_local_demo', stdout=StringIO())
