"""Database configuration shared by runtime and configuration tests."""
import dj_database_url
from django.core.exceptions import ImproperlyConfigured


def database_config(url, sqlite_path, require_postgres=False):
    if not url:
        if require_postgres:
            raise ImproperlyConfigured("DATABASE_URL is required on Cloud Run; refusing ephemeral SQLite.")
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': sqlite_path}
    try:
        config = dj_database_url.parse(url, conn_max_age=60, conn_health_checks=True)
    except Exception:
        raise ImproperlyConfigured('DATABASE_URL must be a valid Postgres connection URL.') from None
    if config['ENGINE'] != 'django.db.backends.postgresql':
        raise ImproperlyConfigured('DATABASE_URL must use Postgres.')
    config['DISABLE_SERVER_SIDE_CURSORS'] = True  # Neon uses transaction pooling.
    config.setdefault('OPTIONS', {}).setdefault('sslmode', 'require')
    config['OPTIONS'].setdefault('connect_timeout', 15)
    config['OPTIONS']['prepare_threshold'] = None
    return config
