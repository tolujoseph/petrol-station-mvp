# Petrol Station MVP

Django REST backend (`backend/`) + React/Vite frontend (`frontend/`).

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) (it installs Python 3.14 for you) and Node.js.

```bash
./dev.sh
```

On first run this installs dependencies, creates the SQLite database and loads demo data, then starts both servers.
To run the setup step alone: `./setup.sh`.

- App: http://localhost:5173
- Django admin: http://localhost:8000/admin/ (the port moves up automatically if 8000 is taken; `dev.sh` prints the real one)

The frontend has its own sign-in screen (Django session login).

## Demo logins

The app is set up for one company, **Omesh**. `python manage.py seed_demo` creates the Omesh station (pumps, pits, prices, checking rules), these logins and the past 2 days of reconciled history (`--days N` for more, `--days 0` for none). Cloud Run uses persistent Postgres and does not run demo seeding. `--reset` wipes every station, record and setting first. The initial demo logins use the password `omesh` (`DEMO_PASSWORD` overrides local seeding). Production keeps its existing accounts and never resets passwords during deployment:

| User | Role |
|---|---|
| `omesh-manager` | Manager (daily entry form) |
| `omesh-owner` | Owner (dashboard, prices, history) |
| `omesh-admin` | Owner + can delete days or clear all records, and use the Django admin |

See `backend/API.md` for the API, including the admin endpoints.


## Owner controls and manual backup

The current production frontend is the separate private `boluwatifeajayi/petrol-station-frontend` repository. The `frontend/` folder in this repository is an older copy.

Owners can create financial columns and hide/restore columns, pumps and tanks from their dashboard. New demo stations start with six PMS pumps, two AGO pumps, and the existing three tanks. Hiding preserves old records. History supports a specific date; managers see only their own records. Owners can correct submitted readings, money and notes; the date and original equipment remain fixed, previous values are recorded, and affected later official results are recalculated.

Before each deployment, sign in as `omesh-admin`, open **Admin**, and choose **Download all data**. Keep the ZIP outside the server. It includes CSV tables, structured operational data, settings, edit history, user identifiers (without credentials), and available photos. `manifest.json` lists missing photo files, if any. This is an export, not an automatic restore feature.

Cloud Run uses Neon Postgres for accounts, entries, settings, and results. These survive restarts and deployments. Uploaded photo files still use ephemeral local storage; continue exporting photos until persistent file storage is configured.


## Production database

Set `DATABASE_URL` to a Postgres URL. The URL is parsed with `dj-database-url` and the backend uses Psycopg 3. TLS URL options (including channel binding) are preserved; server-side cursors and prepared statements are disabled for the transaction pooler. Connections have health checks and a 60-second lifetime. Local development still uses SQLite when the URL is absent. On Cloud Run (`K_SERVICE` set), a missing URL fails startup instead of silently creating an ephemeral database.

The deployment script binds `DATABASE_URL` to the existing GCP Secret Manager secret `petrol-station-database-url` (override its name with `DATABASE_SECRET`, or version with `DATABASE_SECRET_VERSION`). Only the runtime service account needs Secret Accessor on that secret. Do not commit connection strings. `SEED_DEMO=0` in production; the entrypoint also skips seeding whenever Postgres is configured. Migrations still run at startup.

Deploy with `GCP_PROJECT=project-297b4c36-ed50-4f5d-846 ./scripts/deploy-gcp.sh`. The script requires the database secret to exist and retains its binding on future deploys. Existing station configuration was imported from the admin ZIP export. Backups remain available from Admin.
