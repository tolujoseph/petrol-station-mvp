#!/usr/bin/env bash
# Starts the Django backend and the Vite frontend together. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"

FRONTEND_PORT=5173   # fixed: the backend's CORS/CSRF settings allow http://localhost:5173
BACKEND_PORT="${BACKEND_PORT:-8000}"

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# First run? Set everything up automatically.
if [ ! -d frontend/node_modules ] || [ ! -f backend/db.sqlite3 ]; then
  ./setup.sh
fi

# Use the next free port if the default backend port is taken.
while port_busy "$BACKEND_PORT"; do
  echo "Port $BACKEND_PORT is in use, trying $((BACKEND_PORT + 1))"
  BACKEND_PORT=$((BACKEND_PORT + 1))
done
if port_busy "$FRONTEND_PORT"; then
  echo "Port $FRONTEND_PORT is in use. Free it and run again (the backend only allows that origin)."
  exit 1
fi

# Point the frontend at whichever backend port we ended up with.
echo "VITE_API_BASE_URL=http://localhost:${BACKEND_PORT}/api" > frontend/.env.local

trap 'kill 0' EXIT INT TERM
(cd backend && uv run python manage.py runserver "$BACKEND_PORT") &
(cd frontend && npm run dev -- --port "$FRONTEND_PORT" --strictPort) &

cat <<MSG

  App:            http://localhost:${FRONTEND_PORT}
  Django admin:   http://localhost:${BACKEND_PORT}/admin/   <- sign in here first (the app uses this session)
  Demo logins:    manager / owner / admin   password: demo12345

MSG
wait
