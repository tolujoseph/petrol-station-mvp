# Run the backend with Docker

This folder is a complete, standalone backend. You can send someone the entire `backend/` folder, or clone the repository and enter it. You do **not** need Python, uv, Node.js, a frontend, a GCP account, Neon, or Cloudinary installed/configured on the host.

Docker runs Django/Gunicorn and a local Postgres database. Base images are pinned to multi-platform digests and Python dependencies come from `uv.lock`. Maintainers should update those pins deliberately when upgrading the runtime. Database records and local photos are kept in named Docker volumes, so rebuilding or replacing containers keeps your data.

## 1. Install Docker

- **Windows:** install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with the WSL 2 backend. Use Linux containers. Open PowerShell after installation.
- **Mac (Apple Silicon or Intel):** install the matching [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) version. Open Terminal.
- **Linux:** install [Docker Engine](https://docs.docker.com/engine/install/) and the [Compose plugin](https://docs.docker.com/compose/install/linux/).

Start Docker Desktop (or the Docker daemon on Linux), then check:

```console
docker --version
docker compose version
docker info
```

The first build needs internet access to download images and dependencies. Later starts reuse them.

## 2. Start the backend

If you received the whole repository:

```console
cd petrol-station-mvp/backend
```

If you received just the backend folder, open a terminal in that folder instead. It must contain `compose.yaml`, `Dockerfile`, `manage.py`, `pyproject.toml`, `uv.lock`, `config/`, and `daily_ops/`. Do not copy `.venv`, `.env`, or someone else's database files.

Run:

```console
docker compose up --build --wait
docker compose ps
```

No `.env` file is required. Wait until both `db` and `api` are **healthy**. The command starts the containers in the background, waits for Postgres, applies migrations, and creates demo logins/equipment only if the database is empty. Later starts do not reset passwords or records. The initial station has six petrol pumps, two diesel pumps, three tanks and ten configurable financial columns, with no sample daily entries.

Open:

- **Django admin:** http://localhost:8000/admin/
- **API session login:** http://localhost:8000/api-auth/login/?next=/api/auth/me/
- **Signed-in account:** http://localhost:8000/api/auth/me/
- **Unauthenticated smoke check:** http://localhost:8000/api/auth/csrf/

The backend has no homepage: a **404 at `http://localhost:8000/` is expected**. This setup does not run the React frontend.

### Local demo accounts

| Username | Password | Access |
| --- | --- | --- |
| `omesh-manager` | `omesh` | Daily entries and their history |
| `omesh-owner` | `omesh` | Owner settings, prices and corrections |
| `omesh-admin` | `omesh` | Owner, app admin controls and Django admin |

Only `omesh-admin` can sign in to `/admin/`. These are local development accounts, separate from production.

The Compose stack binds the API to your own computer (`127.0.0.1`), does not publish the database port, and uses development credentials. It is **not a production hosting configuration**.

## 3. Verify it works

In a browser, open the smoke-check URL above: it returns JSON with a `csrfToken`.

On macOS/Linux:

```console
curl http://localhost:8000/api/auth/csrf/
```

On Windows PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/api/auth/csrf/
```

Sign in using the API login URL, then open:

- `/api/station/equipment/`
- `/api/station/columns/`
- `/api/station/settings/products/`

The API uses session cookies and CSRF protection. A 403 from a protected endpoint before signing in is expected. When testing writes with Postman/curl, retain the session cookie and send the `csrftoken` cookie value in the `X-CSRFToken` header. See [API.md](API.md) for request formats.

Run the automated backend tests inside Docker:

```console
docker compose exec api python manage.py test daily_ops --noinput
```

Django creates and removes a separate test database; normal local records remain intact.

## Daily commands

Run these from the folder containing `compose.yaml`:

| Task | Command |
| --- | --- |
| Start / rebuild after pulling code | `docker compose up --build --wait` |
| Check status | `docker compose ps` |
| Follow backend logs (Ctrl+C exits logs only) | `docker compose logs -f api` |
| Show database logs | `docker compose logs db` |
| Stop and keep containers/data | `docker compose stop` |
| Remove containers but keep data | `docker compose down` |
| Apply migrations manually | `docker compose exec api python manage.py migrate` |
| Create your own admin | `docker compose exec api python manage.py createsuperuser` |
| Change a local account password | `docker compose exec api python manage.py changepassword omesh-admin` |
| Open Django shell | `docker compose exec api python manage.py shell` |

Source code is copied into the image; it is not bind-mounted. After editing Python files, run `docker compose up --build --wait`. Migrations run automatically on startup. Do not run `seed_demo --reset` unless you intend to erase your local records.

### Where data lives

- `postgres_data`: local Postgres records, users and settings.
- `media_data`: uploaded evidence photos, when Cloudinary is not enabled.

`stop`, `down`, and image rebuilds preserve these volumes. Keep the same Compose project name so Docker reconnects to the same volumes. The default is `petrol-station-backend`.

To deliberately erase **all local database records and local photos** and start fresh:

```console
docker compose down --volumes
docker compose up --build --wait
```

This reset is irreversible without your own backup. It does not remove assets from a separately configured Cloudinary account; delete those through the application's media controls before resetting if needed.

## Optional configuration

Defaults work without changes. To customize, copy `.env.example` to `.env` in this folder (use your editor, `cp .env.example .env` on Mac/Linux, or `Copy-Item .env.example .env` in PowerShell).

| Variable | Default | Purpose |
| --- | --- | --- |
| `BACKEND_PORT` | `8000` | Host port; use `8001` if 8000 is occupied. |
| `LOCAL_FRONTEND_ORIGIN` | `http://localhost:5173` | Additional exact frontend origin allowed for cookies/CSRF/CORS. |
| `LOCAL_CLOUDINARY_URL` | empty | Optional **development** Cloudinary URL. Empty uses persistent local photo storage. |

After changes, run `docker compose up --build --wait`. For `BACKEND_PORT=8001`, use `http://localhost:8001` in all URLs and frontend settings.

The local database URL is explicitly configured in Compose, including `sslmode=disable` for its private local database network. A production `DATABASE_URL` in your shell or `.env` is deliberately not used. Production Neon and Cloudinary secrets stay in GCP Secret Manager; do not send those credentials with the code. Do not commit `.env`.

If using the separate React frontend, set its `VITE_API_BASE_URL=http://localhost:8000/api`, run it as its own project, and use `localhost` consistently for both frontend and backend. A different frontend origin needs `LOCAL_FRONTEND_ORIGIN` set accordingly. The repository's old `frontend/` copy is not the current deployed UI.

## Back up local data

With the database running, these commands work in Terminal and PowerShell without binary shell redirection:

```console
docker compose exec db pg_dump -U petrol_local -d petrol_local -Fc -f /tmp/petrol-local.dump
docker compose cp db:/tmp/petrol-local.dump ./petrol-local.dump
```

For local photos, create a separate archive:

```console
docker compose exec api tar -czf /tmp/petrol-media.tar.gz -C /app/media .
docker compose cp api:/tmp/petrol-media.tar.gz ./petrol-media.tar.gz
```

Keep these files outside the repository. The app's admin export is also available when using the frontend. A Postgres dump does not include photo files.

## Troubleshooting

- **Cannot connect to Docker / daemon not running:** start Docker Desktop, wait for it to be ready, then retry `docker info`. On Linux, follow Docker's install instructions for daemon/user permissions.
- **Port already allocated:** set `BACKEND_PORT=8001` in `.env`, rerun the start command, and use port 8001.
- **No configuration file provided:** you are in the wrong directory. Enter `backend/`, where `compose.yaml` lives.
- **API unhealthy / exited:** run `docker compose logs api db`. Do not erase volumes as a first fix. Migration errors or an interrupted image download should be addressed in those logs.
- **Login rejected:** use `omesh-admin` for Django admin. Existing passwords are preserved on restart; use the `changepassword` command above if necessary.
- **CSRF failure:** use `http://localhost`, not HTTPS, for this local setup; sign in again. Keep frontend/backend hostnames consistent and configure the exact frontend origin.
- **Code changes not visible:** rebuild with `docker compose up --build --wait`.
- **Database appears empty after renaming folders/project:** use the same Compose project name; the default is specified in `compose.yaml`. Do not delete old volumes.
- **Windows shell script error:** the image normalizes the entrypoint's line endings during build. Use the supplied Dockerfile and rebuild instead of running the shell script directly in Windows.

## Deployment distinction

`Dockerfile` and `docker-entrypoint.sh` are also used by GCP Cloud Run. `compose.yaml` supplies local-only settings and a separate local database. This local stack does not change or deploy production. Production does not enable `LOCAL_DEMO`; it uses its existing database/media secrets.

Compose waits for dependencies to become healthy as described in the [Docker startup-order documentation](https://docs.docker.com/compose/how-tos/startup-order/).
