# CleanRoom frontend

React + TypeScript + Vite client for the CleanRoom FastAPI API.

## Setup

```bash
npm install
cp .env.example .env
npm run dev
```

Requests use same-origin `/api` by default. Set `VITE_API_BASE_URL` when the API is served from another origin, for example `http://localhost:8000`.

## Build

```bash
npm run build
```

The client calls `GET /api/health` indirectly through the configured API origin when the audit flow is used, and supports the documented audit, logs, and report endpoints:

- `POST /api/audits`
- `GET /api/audits/{id}`
- `GET /api/audits/{id}/logs`
- `GET /api/audits/{id}/report.json`
- `GET /api/audits/{id}/report.html`
