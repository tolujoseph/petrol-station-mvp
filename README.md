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

The frontend has no login page yet and uses your Django session, so **sign in at the Django admin first**, then open the app.

## Demo logins

Created by `python manage.py seed_demo` (password `demo12345`, override with `DEMO_PASSWORD`):

| User | Role |
|---|---|
| `manager` | Manager (daily entry form) |
| `owner` | Owner |
| `admin` | Manager + Django admin access |

Demo data is for local development only. See `backend/API.md` for the API.
