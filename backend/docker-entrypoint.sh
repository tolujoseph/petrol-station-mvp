#!/usr/bin/env sh
set -e

mkdir -p "$(dirname "${DJANGO_DB_PATH:-/app/data/db.sqlite3}")" "${DJANGO_MEDIA_ROOT:-/app/media}"

python manage.py migrate --noinput

# Demo deployments only: load the Omesh logins, equipment and settings into the (ephemeral) SQLite database,
# plus SEED_DEMO_DAYS days of sample history (default 2; 0 starts with no records).
if [ "${SEED_DEMO:-}" = "1" ]; then
  python manage.py seed_demo --days "${SEED_DEMO_DAYS:-2}"
fi

exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 8 --timeout 120
