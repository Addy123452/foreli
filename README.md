# Foreli

An AI-powered personal prediction system. This is an in-progress, incremental
build. Implemented so far: an interactive dashboard (Overview, Tasks,
Predictions) backed by a real FastAPI + SQLite backend and a transparent
prediction engine.

## What exists today

- `index.html` — premium dark-purple landing page.
- `login.html` / `register.html` — authentication pages (server-side auth).
- `dashboard.html` — interactive dashboard: Overview + Tasks + Predictions.
- `backend/engine.py` — rule-based + statistical prediction engine.
- `backend/auth.py` — PBKDF2 password hashing + SQLite-backed sessions.
- `backend/` — FastAPI app with SQLite persistence (no in-memory demo data).
- `assets/` — frontend CSS and JS.

The AI assistant is **not implemented yet**. Predictions use transparent
rule-based logic plus statistical baselines; a probability value is only shown
when there is a calibrated historical basis (never an arbitrary confidence).
Feedback (accurate/partial/inaccurate) is stored and powers the analytics
accuracy metric; no model retraining is claimed.

## Live preview

- **Static site (GitHub Pages):** <https://addy123452.github.io/foreli/>
  The landing page and UI are live. The interactive app (register / login /
  dashboard) requires the backend to be deployed separately — see *Deployment*.
  Login pages show a "static preview" notice when hosted without the API.

## Requirements

- Python 3.11+ with `fastapi` and `uvicorn` (see `backend/requirements.txt`).

## Install

```powershell
cd C:\Users\adity\Downloads\foreli
python -m pip install -r backend\requirements.txt
```

## Run the backend

```powershell
cd C:\Users\adity\Downloads\foreli
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Then open one of:

- <http://127.0.0.1:8000/> — landing page
- <http://127.0.0.1:8000/dashboard> — dashboard

Access the app through the backend URL (same origin) so the session cookie
works: <http://127.0.0.1:8000/login.html>.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/stats` | Aggregate dashboard counts |
| GET | `/api/tasks` | List tasks (`q`, `status`, `priority` query filters) |
| POST | `/api/tasks` | Create a task |
| GET | `/api/tasks/{id}` | Get one task |
| PATCH | `/api/tasks/{id}` | Update a task (partial) |
| DELETE | `/api/tasks/{id}` | Delete a task |
| POST | `/api/tasks/{id}/toggle` | Toggle done ↔ todo |
| GET | `/api/predictions` | List predictions (`status=active\|resolved\|all`) |
| POST | `/api/predictions/refresh` | Re-generate predictions from current tasks |
| GET | `/api/predictions/{id}` | Get one prediction |

## Data

SQLite database file: `backend/foreli.db` (auto-created on first start).
Schema is managed by an explicit migration list in `backend/db.py` using
`PRAGMA user_version`.

Timestamps are stored as naive local ISO 8601 strings (server and browser share
the same machine). A later milestone will migrate to UTC + timezone.

## Verify

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
python -m backend.engine_smoke_test
python -m backend.test_phase6_routing
python -m backend.test_phase7_live
```

## Authentication

- Passwords are hashed with PBKDF2-HMAC-SHA256 (per-user salt); sessions are
  random tokens stored in SQLite and sent as an **HttpOnly** cookie.
- `/api/tasks*`, `/api/predictions*`, and `/api/stats` require a valid session
  (401 otherwise). `GET /api/health` and the auth routes are public.
- Register at `/register.html`, sign in at `/login.html`. The dashboard redirects
  to login when unauthenticated and after sign-out.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register` | Create account + session |
| POST | `/api/auth/login` | Sign in + session |
| POST | `/api/auth/logout` | End session |
| GET | `/api/auth/me` | Current user (401 if not signed in) |

**Password reset:** `POST /api/auth/forgot` generates a single-use, 30-minute
token (stored hashed) and `POST /api/auth/reset` sets a new password and signs
out all existing sessions. Email delivery is not configured, so the reset link is
written to the server log and shown locally at `/forgot.html`. Email verification
is not implemented.

## Environment variables

See `.env.example`. Backend (server-side only): `FORELI_CORS_ORIGINS`,
`FORELI_COOKIE_SECURE`, optional `FORELI_DB_PATH`. Frontend (public): set the API
origin in `assets/js/config.js` (`window.FORELI_API_BASE`). Never put secrets in
frontend files.

## Deployment (Vercel)

Foreli is a static frontend plus a separate FastAPI/SQLite backend.

- **Frontend → Vercel:** deploy the repo root as a static site. `vercel.json`
  adds rewrites for `/login`, `/register`, `/dashboard`. Before deploying, set
  `window.FORELI_API_BASE` in `assets/js/config.js` to the deployed backend URL.
- **Backend → separate host:** the FastAPI app uses a local SQLite file and a
  long-running server, so **it cannot run as standard Vercel serverless functions
  with persistent data**. Host it where persistent disk exists (Render, Railway,
  Fly.io, or a VPS), set `FORELI_CORS_ORIGINS` to the Vercel URL and
  `FORELI_COOKIE_SECURE=1` (HTTPS), and mount a volume for `backend/foreli.db`.
- **Checklist:**
  1. Set `FORELI_CORS_ORIGINS` and `FORELI_COOKIE_SECURE=1` on the backend host.
  2. Mount persistent storage for the SQLite DB (or migrate to Postgres).
  3. Set `window.FORELI_API_BASE` in `assets/js/config.js`.
  4. Deploy the frontend to Vercel and the backend to the persistent host.
  5. Verify `/api/health`, register, login, and a protected request.

## One-container deploy (Render / Railway / Fly.io)

The `Dockerfile` builds a single container that runs the FastAPI backend **and**
serves the static frontend from the same origin, so the whole app works at one
URL (no separate frontend host needed).

- **Render:** `render.yaml` is a ready blueprint — create a new Blueprint, point
  it at this repo, and deploy. A **persistent disk** mounted at `/data` is required
  so `backend/foreli.db` survives restarts (on ephemeral free plans, data resets).
- **Railway / Fly.io:** use the `Dockerfile` / `Procfile`, mount a volume at
  `/data`, and set `FORELI_DB_PATH=/data/foreli.db`.
- **Environment:** set `FORELI_COOKIE_SECURE=1` (HTTPS). If you host the frontend
  separately (e.g. GitHub Pages), also set `FORELI_CORS_ORIGINS` to that origin
  and point `assets/js/config.js` at this backend URL.

> **Note:** Foreli is currently single-tenant — all accounts share the same task
> data. Do not share a public deployment with other people until per-user data
> scoping is implemented.
