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

The app is set up for one company, **Omesh**. `python manage.py seed_demo` creates the Omesh station (pumps, pits, prices, checking rules), these logins and the past 2 days of reconciled history (`--days N` for more, `--days 0` for none). The Cloud Run deployment starts with no records (`SEED_DEMO_DAYS`, default 0 in `scripts/deploy-gcp.sh`). `--reset` wipes every station, record and setting first. All logins use the password `omesh` (override with `DEMO_PASSWORD`), locally and on the Cloud Run deployment:

| User | Role |
|---|---|
| `omesh-manager` | Manager (daily entry form) |
| `omesh-owner` | Owner (dashboard, prices, history) |
| `omesh-admin` | Owner + can delete days or clear all records, and use the Django admin |

See `backend/API.md` for the API, including the admin endpoints.
