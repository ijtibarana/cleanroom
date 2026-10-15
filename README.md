# CleanRoom

> **Works on my machine? Prove it.**

CleanRoom is a local-first repository reproducibility auditor. It inspects a selected JavaScript/TypeScript or Python repository and returns evidence-backed results for eight checks: Git history, dependency locking, runtime pinning, Docker verification, test command verification, README instructions, `.env.example`, and suspicious absolute paths.

## What is included

- FastAPI backend with deterministic repository inspection.
- React + TypeScript + Vite browser interface.
- Truthful result states: `PASS`, `FAIL`, `UNVERIFIED`, and `SKIPPED`.
- JSON and standalone HTML report exports.
- Secret redaction in evidence and verification output.
- Safe repository scanning that does not follow symlinks outside the selected repository.
- Optional Docker verification with `--network=none`, no host Docker socket, dropped capabilities, read-only runtime, and a temporary filesystem.

The MVP does not run project scripts directly on the host. Docker verification is marked `UNVERIFIED` when Docker is not installed or when a successful image build is unavailable.

## Requirements

- Linux with Python 3.11.2.
- Node.js 22.23.3 for the frontend.
- Docker is optional for static audits and required only for Docker build/test verification.

The pinned versions are recorded in `.python-version`, `frontend/.nvmrc`, and `frontend/package-lock.json`. Python dependency pins are in `backend/requirements.lock`.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.lock

cd frontend
npm ci
cd ..
```

No API keys or cloud services are required. `.env.example` contains placeholders only.

## Run locally

Start the API in one terminal:

```bash
python3 -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Start the Vite UI in another terminal:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>, enter a repository path visible to the API process, and choose **Start audit**. The API is also available at <http://localhost:8000/docs>.

For a frontend-only preview without a backend, build the included sample audit mode:

```bash
cd frontend
VITE_DEMO_MODE=true npm run build
python3 -m http.server 4173 --directory dist
```

This preview is clearly labeled as sample data and keeps the real API mode as the default.

To serve the built UI from the API, build the frontend and run the API from the repository root:

```bash
cd frontend && npm run build && cd ..
python3 -m uvicorn app.main:app --app-dir backend --port 8000
```

Then open <http://localhost:8000>.

## Test

The single project check command runs backend tests and the production frontend build:

```bash
make test
```

The backend tests exercise healthy, incomplete, and unsafe repository scenarios, missing paths, secret redaction, escaping symlinks, API validation, and report parity.

## Docker

Build and run the application:

```bash
docker compose build
docker compose up
```

Open <http://localhost:8000>. The application container does not mount the host Docker socket. This is intentional: an audited repository must not receive host Docker control.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Backend availability |
| POST | `/api/audits` | Run an audit; body is `{ "repo_path": "/path/to/repo", "verify_docker": true, "verify_tests": true }` |
| GET | `/api/audits/{id}` | Retrieve the audit record |
| GET | `/api/audits/{id}/logs` | Retrieve verification logs |
| GET | `/api/audits/{id}/report.json` | Download JSON report |
| GET | `/api/audits/{id}/report.html` | Open standalone HTML report |

Audit history is process-local for this MVP. Restarting the API clears stored audit records.

## Project layout

```text
backend/app/       Analyzer, API models, report renderers, and in-memory store
backend/tests/     Offline pytest coverage
frontend/src/      React interface and typed API client
fixtures/          Fixture repository space for local demonstrations
docs/               Requirements and implementation notes
```

## Security notes

Repositories are untrusted input. CleanRoom does not execute repository code on the host, disables network access for Docker commands, limits Docker command duration, redacts credential-like values, and refuses to read through escaping symlinks. Container isolation is not a complete security boundary; use a dedicated machine or stronger sandbox for hostile repositories.
