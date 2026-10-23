#!/usr/bin/env bash
# Deploys the Django backend to Cloud Run as its own service (demo setup: SQLite, data resets on restart).
# Usage: GCP_PROJECT=<project-id> ./scripts/deploy-gcp.sh
set -euo pipefail
cd "$(dirname "$0")/../backend"

PROJECT="${GCP_PROJECT:?Set GCP_PROJECT to the target project id}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="${GCP_SERVICE:-petrol-station-api}"
EXTRA_ORIGINS="${FRONTEND_ORIGINS:-}"   # comma-separated deployed frontend origins, e.g. https://app.example.com

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SERVICE_URL="https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"

# Reuse secrets from an existing deployment so redeploys don't invalidate sessions or change the demo password.
existing() { gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --format="value(spec.template.spec.containers[0].env.filter(name:$1).extract(value).flatten())" 2>/dev/null || true; }
SECRET_KEY="$(existing DJANGO_SECRET_KEY)"; SECRET_KEY="${SECRET_KEY:-$(openssl rand -base64 48 | tr -d '\n/+=')}"
DEMO_PASSWORD_VALUE="$(existing DEMO_PASSWORD)"; DEMO_PASSWORD_VALUE="${DEMO_PASSWORD_VALUE:-$(openssl rand -base64 18 | tr -d '\n/+=')}"

ENV_FILE="$(mktemp)"; trap 'rm -f "$ENV_FILE"' EXIT
cat > "$ENV_FILE" <<YAML
DJANGO_DEBUG: "false"
DJANGO_SECRET_KEY: "${SECRET_KEY}"
DJANGO_ALLOWED_HOSTS: ".run.app,localhost"
DJANGO_CSRF_TRUSTED_ORIGINS: "${SERVICE_URL}"
DJANGO_CORS_ALLOWED_ORIGINS: "${EXTRA_ORIGINS}"
DJANGO_BEHIND_PROXY: "true"
DJANGO_DB_PATH: "/app/data/db.sqlite3"
DJANGO_MEDIA_ROOT: "/app/media"
SEED_DEMO: "1"
DEMO_PASSWORD: "${DEMO_PASSWORD_VALUE}"
YAML

# One instance only: SQLite lives on the instance's local disk.
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source . \
  --allow-unauthenticated --min-instances 1 --max-instances 1 --memory 512Mi \
  --env-vars-file "$ENV_FILE" --quiet

echo
echo "Service:        $SERVICE_URL"
echo "Django admin:   $SERVICE_URL/admin/"
echo "Demo logins:    manager / owner / admin   password: $DEMO_PASSWORD_VALUE"
