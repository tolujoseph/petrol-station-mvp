#!/usr/bin/env bash
# One-time setup: installs dependencies, creates the database and loads demo data.
set -euo pipefail
cd "$(dirname "$0")"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing '$1'. $2"; exit 1; }; }
need uv  "Install it from https://docs.astral.sh/uv/ (brew install uv)"
need npm "Install Node.js from https://nodejs.org"

echo "==> Backend: installing dependencies"
(cd backend && uv sync)

echo "==> Backend: migrating database"
(cd backend && uv run python manage.py migrate --noinput)

echo "==> Backend: loading demo data"
(cd backend && uv run python manage.py seed_demo)

echo "==> Frontend: installing dependencies"
(cd frontend && npm ci)

echo
echo "Setup complete. Start everything with:  ./dev.sh"
