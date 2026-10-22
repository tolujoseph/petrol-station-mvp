# Javeln Petrol Station Frontend

React + Vite frontend for the petrol-station daily operations MVP.

## Requirements

- Node.js compatible with the version supported by the installed Vite release.
- The Django backend running and accessible to this browser.

## Local development

1. Install dependencies with `npm ci`.
2. Copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL` to the backend API base URL.
3. Start the frontend with `npm run dev`.

The frontend uses the backend's session authentication and CSRF protection. Sign in through the configured Django session before using the application.

## Daily-entry workflow

- Select the pumps and tanks used for the business date.
- Enter closing readings and any financial transactions.
- Attach evidence photos to every selected pump and tank reading.
- **Submit entry** saves the latest changes and asks the backend to finalise reconciliation.
- **Save and continue later** persists a draft that can be resumed from Saved drafts.
- **Cancel entry** exits the form after confirmation. An existing saved draft is kept.
- **Discard** permanently removes a saved draft only after a separate confirmation.

## Commands

- `npm run dev` — local development server.
- `npm run build` — production build.
- `npm run lint` — lint the source code.
