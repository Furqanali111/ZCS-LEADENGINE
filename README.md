# ZCS LeadEngine

Internal, single-user, local-first tool for Zenith Care Solutions. It finds U.S. healthcare practices through the CMS NPI Registry, scores and prioritizes them, tracks leads through a sales pipeline, and exports to Excel. Slices 1 (lead discovery) and 2 (CRM). Read `CLAUDE.md` and the PRD before changing anything.

## Prerequisites

- Windows, Python 3.12 (`py -3.12`), Node 22
- A Supabase project (Postgres). Use the **session pooler** connection string if your network has no IPv6.

## Backend setup

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

In `backend/.env`, set `DATABASE_URL` (percent-encode special characters in the password, `@` = `%40`, `#` = `%23`). Never commit `.env`. Then create the tables (`alembic upgrade head` applies all migrations, including 0004 for activities and the suppression list). Run it with the venv active; the global `alembic` fails with `No module named 'app'`:

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
cd backend; .venv\Scripts\activate; uvicorn app.main:create_app --factory --reload --port 8000
```

```powershell
cd frontend; npm run dev
```

Open http://localhost:3000.

| Page | Path | Purpose |
|---|---|---|
| Dashboard | `/` | Tiles, breakdowns, conversion as converted / contacted |
| Search | `/search` | Start and watch discovery jobs |
| Leads | `/leads` | List, filter, sort, export |
| Lead detail | `/leads/[id]` | Status, follow-up, activity log, score, contacts |
| Pipeline | `/pipeline` | Kanban board by status |
| Suppression | `/suppression` | Do-not-contact list |

New API routes (slice 2):

| Route | Purpose |
|---|---|
| `GET/PATCH /api/leads/{id}` | Lead detail, change status or follow-up date |
| `GET/POST /api/leads/{id}/activities` | Activity timeline, log a call, email, meeting or note |
| `GET /api/pipeline`, `GET /api/pipeline/{status}` | Board columns and paged cards |
| `GET /api/dashboard/stats` | Dashboard figures for a date range |
| `GET/POST /api/suppression`, `DELETE /api/suppression/{id}` | Suppression list |

Suppression email entries are stored now but only start blocking in slice 3, when emails are collected.

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
