from django.test import SimpleTestCase
from django.core.exceptions import ImproperlyConfigured
from config.database import database_config


class DatabaseConfigTests(SimpleTestCase):
    def test_local_development_still_supports_sqlite(self):
        self.assertEqual(database_config(None, '/tmp/dev.sqlite3'), {'ENGINE': 'django.db.backends.sqlite3', 'NAME': '/tmp/dev.sqlite3'})

    def test_neon_ssl_and_pooler_options(self):
        config = database_config('postgresql://test:encoded%40password@db.example.test/demo?sslmode=require&channel_binding=require', '/tmp/unused')
        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['PASSWORD'], 'encoded@password')
        self.assertEqual(config['OPTIONS']['sslmode'], 'require')
        self.assertEqual(config['OPTIONS']['channel_binding'], 'require')
        self.assertIsNone(config['OPTIONS']['prepare_threshold'])
        self.assertTrue(config['DISABLE_SERVER_SIDE_CURSORS'])
        self.assertTrue(config['CONN_HEALTH_CHECKS'])

    def test_invalid_database_never_silently_falls_back_to_sqlite(self):
        for url in ['not-a-url', 'sqlite:///tmp/db', 'mysql://user:private@host/db']:
            with self.assertRaises(ImproperlyConfigured) as error:
                database_config(url, '/tmp/unused')
            self.assertNotIn('private', str(error.exception))

    def test_cloud_run_requires_postgres(self):
        with self.assertRaises(ImproperlyConfigured):
            database_config(None, '/tmp/unused', require_postgres=True)
