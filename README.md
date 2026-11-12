# ZCS LeadEngine

Internal, single-user, local-first tool for Zenith Care Solutions. It finds U.S. healthcare practices through the CMS NPI Registry, scores and prioritizes them, tracks leads through a sales pipeline, and exports to Excel. Slices 1 (lead discovery), 2 (CRM) and 3 (enrichment). Read `CLAUDE.md` and the PRD before changing anything.

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

In `backend/.env`, set `DATABASE_URL` (percent-encode special characters in the password, `@` = `%40`, `#` = `%23`). For enrichment also set `BRAVE_API_KEY` (see below). Never commit `.env`. Then create the tables (`alembic upgrade head` applies all migrations, including 0004 for activities and the suppression list). Run it with the venv active; the global `alembic` fails with `No module named 'app'`:

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

Suppression email entries block collected emails (slice 3).

## Enrichment (slice 3)

The search page has an enrichment toggle. When on, after the NPI phases the job looks up each lead's practice website through the Brave Search API, then reads the practice's own public pages for emails and named staff.

Setup:

1. Put `TAVILY_API_KEY=...` (or `BRAVE_API_KEY=...`) in `backend/.env`. Never commit it. Tavily is used when its key is set, otherwise Brave.
2. Run `alembic upgrade head` (migration 0005 adds the website, email and enrichment columns and seeds the sources).
3. Brave and the practice websites start as `approved_not_built`. After you confirm Brave's storage terms (see `docs/data-sources.md`), run this yourself in the Supabase SQL editor. No code runs it:

```sql
update source_configs set status='available' where key in ('tavily_search','practice_websites');
```

Fallback (optional): read DuckDuckGo's acceptable use policy first. If you accept it, run `update source_configs set status='available' where key='duckduckgo_search';` and the job switches to the `ddgs` library once Tavily reports its credits used up. It stays off otherwise.

4. Re-run `python -m app.rescore` once after upgrading (scoring config v2 counts staff contacts as decision-makers).

Rules:

- robots.txt is respected, including Crawl-delay, at about 1 request per second per domain. No logins, CAPTCHAs or bypasses.
- A website is accepted only when an automatic check passes (the page shows the lead's phone, or its name and city). Wrong ones can be rejected on the lead page.
- Email status is "found on page", not verified. Nothing is sent to anyone.
- Yelp is rejected by its terms and is never used.
- Brave results are used in memory only. Only the verified website URL is stored.

Optional env: `ENRICH_PAGE_DELAY_SECONDS` (default 1) is the minimum wait between requests to the same website; robots.txt Crawl-delay can raise it.

The job list shows the enrichment counters. `pages_fetched` counts NPI pages plus web pages for enrich jobs, and `skipped` (shown as "pages skipped") counts pages not read: non-HTML, too large, CAPTCHA, failed redirects, or hosts that are not public websites. Only leads linked to an enrich job are enriched.

Route changes:

| Route | Change |
|---|---|
| `POST /api/search` | Accepts `enrich`. Returns 422 `source_not_available` or `missing_api_key` when it cannot run |
| `GET /api/leads` | New filters `has_website` and `has_email` |
| `PATCH /api/leads/{id}` | `reject_website` clears the website and its web contacts |

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
