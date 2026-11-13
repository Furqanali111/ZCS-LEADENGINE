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
| Lead detail | `/lead?id=<id>` | Status, follow-up, activity log, score, contacts |
| Pipeline | `/pipeline` | Kanban board by status |
| Suppression | `/suppression` | Do-not-contact list |
| Templates | `/templates` | Saved email and call templates, copied by hand from lead detail. Nothing is sent |

New API routes (slice 2):

| Route | Purpose |
|---|---|
| `GET/PATCH /api/leads/{id}` | Lead detail, change status or follow-up date |
| `GET/POST /api/leads/{id}/activities` | Activity timeline, log a call, email, meeting or note |
| `GET /api/pipeline`, `GET /api/pipeline/{status}` | Board columns and paged cards |
| `GET /api/dashboard/stats` | Dashboard figures for a date range |
| `GET/POST /api/suppression`, `DELETE /api/suppression/{id}` | Suppression list |
| `GET/POST /api/templates`, `PATCH/DELETE /api/templates/{id}` | Outreach templates (copy-only, migration 0007) |
| `GET/POST /api/saved-searches`, `DELETE /api/saved-searches/{id}`, `POST /api/saved-searches/{id}/touch` | Saved search forms (migration 0012). `X-Salesperson` is stored as `created_by`, `touch` sets `last_run_at` |

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

Fallback (optional): you accepted DuckDuckGo's [acceptable use policy](https://duckduckgo.com/acceptable-use) risk (it does not mention automated access either way; see `docs/data-sources.md`). To turn the fallback on, run `update source_configs set status='available' where key='duckduckgo_search';` and the job switches to the `ddgs` library once Tavily reports its credits used up. It stays off otherwise.

4. Re-run `python -m app.rescore` once after upgrading (scoring config v3: staff contacts count as decision-makers, and the priority tiers are critical 95, high 90, medium 80).

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
| `GET/DELETE /api/search/progress` | How many new leads a search has already fetched, and reset it (Start over). `target_count` now allows up to 50,000 |

## Salespeople, claiming leads (migration 0011)

There are no accounts. Each salesperson types their name once at the top right of the page (kept in that browser, sent as the `X-Salesperson` header). **Claim this lead** sets the owner and moves a new lead to In progress; choosing In progress in the Sales status dropdown claims it too. A claim is atomic: if someone else already owns the lead the server answers 409 `already_claimed` with their name. Owners show in the Leads table, the Pipeline cards and the lead page, and the Leads page has an Owner filter (Mine, Unclaimed, or a name). The name says who did something, it does not prove it: anyone on your network can send any name.

On a lead page, the call-result buttons (No answer, Spoke call back, Interested, Not interested) log the call, set the follow-up date and status, then open the next lead: your own due follow-ups first, else the best unclaimed new lead, claimed for you.

| Route | Change |
|---|---|
| `POST /api/leads/{id}/claim`, `POST /api/leads/{id}/release` | Take or give back a lead |
| `GET /api/owners` | Names that currently own a lead |
| `GET /api/leads/{id}/related` | Up to 20 other leads sharing a phone, normalized name, parent organization, authorized official or website domain, with a `reasons` list each (computed live, no table) |
| `GET /api/leads` | New filter `owner` (a name, or `none` for unclaimed) |
| Activities | Each new activity stores `actor`, the salesperson name |

## Enrich leads you already have

`python -m app.enrich_existing --limit 10 [--state TX] [--priority critical]` takes the best-scored leads that have no website yet, links them to a new job (shown in the Searches list as "Enrich existing leads") and runs the normal enrichment pass. It spends one search query per lead.

## Hospital phones and hours from Google Maps

Hospitals get a second phone number and opening hours from the public Google Maps page (see `docs/data-sources.md` for the terms and the accepted risk). One-time setup in the backend venv: `pip install playwright` then `playwright install chromium` (about 150 MB). Then run migration 0015 (`alembic upgrade head`).

- On a hospital's lead page, **Look up on Google Maps** runs one lookup (about 15 seconds).
- In bulk: `python -m app.enrich_maps --limit 10 --state TX` takes the best-scored hospitals not yet checked, one every few seconds, and stops at once if Google asks for a CAPTCHA.
- The NPI phone is never replaced. The Maps phone is saved beside it with its source and date, flagged when it differs. Every phone on the lead card has a Copy button, and the card links to the same Maps search so a salesperson can check by hand.

## Tests

```powershell
cd backend; .venv\Scripts\activate; pytest -q
cd frontend; npm test; npm run lint; npx tsc --noEmit; npm run build
```

Backend tests start an embedded Postgres (`pgserver`), no Docker and never the real database. Set `TEST_DATABASE_URL` to use another empty database instead.

## Re-score after editing the scoring config

Scoring weights live in `backend/scoring_config.json`. After changing them:

```powershell
cd backend; python -m app.rescore
```

Config v4: the decision-maker factor (max 15) pays 6 for a named official with a title and 9 more only when we can reach them directly (their own phone, different from the office line, or a found email). Office line only earns no reachability points.

## Notes

- Sources are opt-in: only sources marked `available` in `docs/data-sources.md` can be searched.
- Fit score, priority and conversion probability are different things. Slice 1 has no conversion probability.
- Searches continue where the last one stopped: the app saves, per specialty, state, city and the subparts and hospitals toggles, how far it has read, so a repeat search returns new leads only (the target counts new leads). One NPI query returns at most 1,200 records, so when a search hits that cap it is split by ZIP prefix automatically. Use Start over on the search form to read from the beginning again. Saved leads are never deleted by that.
- Not built yet: see `docs/deferred-items.md`.

## Desktop app and automatic updates

Teammates run one Windows app instead of two dev servers. It serves the UI and the API on `http://127.0.0.1:8005`, runs pending database migrations on start (guarded by a Postgres advisory lock, so two people starting at once is safe), and updates itself.

**First install (each teammate):**
1. Download `zcs-leadengine-vX.Y.Z.zip` from the repository's Releases page and unzip it anywhere.
2. Copy `.env.example` to `.env` next to `zcs-leadengine.exe` and fill in `DATABASE_URL` (the admin sends the real values privately; never commit them).
3. Double-click `zcs-leadengine.exe`. Windows SmartScreen may warn "unknown publisher" because the exe is not code-signed: More info, then Run anyway.

**Updates:** every start checks the latest GitHub release. If it is newer, the app downloads it, verifies the checksum, swaps the files (your `.env` is never touched) and restarts. If the check fails (offline, rate limited), the current version starts. Set `ZCS_NO_UPDATE=1` to skip the check. For a private repository, put a read-only fine-grained token (Contents: read) in `.env` as `ZCS_UPDATE_TOKEN`. `ZCS_UPDATE_REPO` and `ZCS_PORT` (default 8005) are optional overrides.

**Releasing (maintainer):** cut `release/vX.Y.Z` from `develop`, then tag and push:

```powershell
git tag vX.Y.Z; git push origin vX.Y.Z
```

The `release` workflow builds the UI (`STATIC_EXPORT=1`, same-origin API), bundles it with PyInstaller and attaches the zip to a GitHub Release. The `ci` workflow runs backend tests, frontend lint, tests and both builds on every pull request.

Limits: Windows only; the app updates only when it starts (a long-running window keeps the old version until restarted); every teammate's `.env` holds the database URL, which is full access to the data, fine for a trusted team; migrations run from every client, so keep them additive and backward compatible.

### Quick build: one .exe for the team (no GitHub needed)

**Build it** (on your PC, about 2 minutes; stop the dev servers first). From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-test-exe.ps1 -Port 8005
```

`-Port` is the port the app will use on the teammate's PC (default 8005). It is baked into the exe; your own `backend\.env` is not changed. This creates `backend\dist\zcs-leadengine.exe`: one file with the UI, the migrations and your `backend\.env` packed inside. It needs Node and the backend `.venv` already set up on your PC.

**Share it:** send that one file privately (USB, private chat). Never upload it anywhere public, because the database URL is inside it and anyone can extract it. To keep a teammate off the real data, point `backend\.env` at another database before building.

**Teammate steps:**
1. Double-click `zcs-leadengine.exe`. If Windows SmartScreen warns "unknown publisher", click More info, then Run anyway.
2. The browser opens `http://127.0.0.1:<port>` (8005 unless you built with another `-Port`). Keep the black window open while using the app: closing it stops the app.

**New version later:** pull the latest `develop`, run the build command again, and send the new file. This build does not self-update (only the zipped GitHub release build does).
