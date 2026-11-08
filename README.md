# Petrol Station MVP

Django REST backend (`backend/`) + React/Vite frontend (`frontend/`).

## Backend only with Docker (recommended for sharing)

Install Docker Desktop, start it, then run:

```console
cd backend
docker compose up --build --wait
```

Open http://localhost:8000/admin/ and sign in with `omesh-admin` / `omesh`.
Docker supplies Python, dependencies and a local Postgres database; no production credentials are needed. Data and photos persist across restarts. See the [backend Docker README](backend/README.md) for Windows/Mac/Linux setup, API URLs, configuration, testing, backups and troubleshooting. You can share the entire `backend/` folder on its own.

## Legacy combined development setup

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

Cloud Run uses Neon Postgres for accounts, entries, settings, and results. These survive restarts and deployments. Reading photos use private Cloudinary storage and survive deployments. Admins can download a separate media ZIP and delete selected photos from the Admin media gallery. Photos appear beside their pump/tank readings.


## Production database

Set `DATABASE_URL` to a Postgres URL. The URL is parsed with `dj-database-url` and the backend uses Psycopg 3. TLS URL options (including channel binding) are preserved; server-side cursors and prepared statements are disabled for the transaction pooler. Connections have health checks and a 60-second lifetime. Local development still uses SQLite when the URL is absent. On Cloud Run (`K_SERVICE` set), a missing URL fails startup instead of silently creating an ephemeral database.

The deployment script binds `DATABASE_URL` to the existing GCP Secret Manager secret `petrol-station-database-url` (override its name with `DATABASE_SECRET`, or version with `DATABASE_SECRET_VERSION`). Only the runtime service account needs Secret Accessor on that secret. Do not commit connection strings. `SEED_DEMO=0` in production; the entrypoint also skips seeding whenever Postgres is configured. Migrations still run at startup.

Deploy with `GCP_PROJECT=project-297b4c36-ed50-4f5d-846 ./scripts/deploy-gcp.sh`. The script requires the database secret to exist and retains its binding on future deploys. Existing station configuration was imported from the admin ZIP export. Backups remain available from Admin.

### Cloudinary media

Set `CLOUDINARY_URL` on the backend only. Cloud Run binds Secret Manager `petrol-station-cloudinary-url`; production startup fails without it. Local development without this variable uses filesystem storage. Uploads are authenticated Cloudinary assets with backups disabled; the application checks station/role access before serving photos. Credentials and private signed delivery URLs are never sent to the frontend.

Admin endpoints: `GET /api/admin/media/` (optional `before=YYYY-MM-DD` and `page`), `GET /api/admin/media/export/`, and `POST /api/admin/media/delete/` with `{"confirm":"DELETE MEDIA","items":[{"type":"pump","id":123}]}` (up to 20 per request). Deletion destroys the Cloudinary original, requests CDN invalidation, and verifies the asset is absent through the Cloudinary origin API before removing its database record. Readings and financial data remain intact. A failed removal stays listed for retry.

Deleting an entry also queues its photo removals after the database transaction commits. Failed cleanup is retained in `MediaDeletionJob`; admins can retry it from the gallery (`POST /api/admin/media/retry/`). Operators can run `python manage.py retry_media_deletions` to process pending jobs, including deleted stations. Downloaded ZIP copies are independent of Cloudinary deletion.
