#!/usr/bin/env sh
set -e

mkdir -p "$(dirname "${DJANGO_DB_PATH:-/app/data/db.sqlite3}")" "${DJANGO_MEDIA_ROOT:-/app/media}"

python manage.py migrate --noinput

# Demo deployments only: load demo users, settings and history into the (ephemeral) SQLite database.
if [ "${SEED_DEMO:-}" = "1" ]; then
  python manage.py seed_demo
fi

exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 8 --timeout 120
