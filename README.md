# ZCS LeadEngine

Internal, single-user, local-first tool for Zenith Care Solutions. It finds U.S. healthcare practices through the CMS NPI Registry, scores and prioritizes them, tracks a simple sales status, and exports to Excel. Slice 1 (lead discovery) only. Read `CLAUDE.md` and the PRD before changing anything.

## Prerequisites

- Windows, Python 3.12 (`py -3.12`), Node 22
- A Supabase project (Postgres). Use the **session pooler** connection string if your network has no IPv6.

## Backend setup

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
copy .env.example .env
```

Edit `backend/.env`: set `DATABASE_URL` (percent-encode special characters in the password, `@` = `%40`, `#` = `%23`). Never commit `.env`. Then create the tables:

```powershell
alembic upgrade head
```

## Frontend setup

```powershell
cd frontend
npm install
copy .env.example .env.local
```

## Run

Two terminals:

```powershell
cd backend; .venv\Scripts\activate; uvicorn app.main:app --factory --port 8000
```

```powershell
cd frontend; npm run dev
```

Open http://localhost:3000. Search page starts a job, Leads page lists, filters and exports.

## Tests

```powershell
cd backend; .venv\Scripts\activate; pytest -q
cd frontend; npm run lint; npx tsc --noEmit; npm run build
```

Backend tests start an embedded Postgres (`pgserver`), no Docker and never the real database. Set `TEST_DATABASE_URL` to use another empty database instead.

## Re-score after editing the scoring config

Scoring weights live in `backend/scoring_config.json`. After changing them:

```powershell
cd backend; python -m app.rescore
```

## Notes

- Sources are opt-in: only sources marked `available` in `docs/data-sources.md` can be searched.
- Fit score, priority and conversion probability are different things. Slice 1 has no conversion probability.
- One NPI query returns at most 1,200 records. Use the optional city filter to go deeper.
- Not built yet: see `docs/deferred-items.md`.
