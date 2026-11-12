# Slice 1: Lead Discovery, Design Spec

**Status:** Draft for owner review
**Date:** 2026-11-11
**Parent docs:** `ZCS_LeadEngine_Architectural_PRD.md` (section 15, slice 1), `docs/data-sources.md`

## 1. Goal

A ZCS sales operator can, on their own computer, search for U.S. healthcare practices by specialty and state, get real organizations saved to Supabase, see each one scored and prioritized with reasons, set a sales status, and export a filtered list to Excel.

Success for this slice: a search for "Internal Medicine, TX, 500" finishes with up to 500 real, scored leads in the table, survives a backend restart mid-search without duplicates, and exports to a workbook that opens in Excel.

## 2. Scope

In scope (PRD FR-01, FR-02, FR-03, FR-08, FR-13, FR-14, FR-15, the table and filter parts of FR-11, and FR-07 by NPI only):

- Search form with specialty, state, optional city, target count, inclusion toggles, and source selection
- Two kinds of lead: practices (organization NPI records) and solo doctors (individual NPI records marked as sole proprietors)
- Persistent, resumable search jobs with progress counters
- One connector: CMS NPI Registry API
- Organizations, locations, contacts (the authorized official), and source records saved to Supabase
- Deduplication by NPI
- Fit score (0 to 100), priority tier, and human-readable reasons
- Leads table with search, filters, sorting, pagination, and an editable sales status
- Excel export of filtered or selected leads

Out of scope, tracked in `docs/deferred-items.md`: lead detail page, activity history, follow-ups, suppression list, pipeline, dashboard, websites, emails, directories, the bulk NPPES file, cross-source dedup, conversion probability, authentication, automated frontend tests.

## 3. Facts about the NPI Registry API (tested 2026-11-11)

These shape the design:

- At most 200 records per page. `skip` is capped at 1000, so one query returns at most 1,200 records. A `skip` above 1000 silently returns the last page again.
- Result order is stable between identical calls. The API does not report a total count.
- `state` alone is refused. State plus `taxonomy_description` plus `enumeration_type=NPI-2` works.
- `city` and `postal_code` (with a trailing `*` wildcard) work as extra filters.
- `taxonomy_description` matches any of an organization's taxonomies, not only the primary one. A search for Internal Medicine returned some organizations whose primary taxonomy is Family Medicine or a clinic type. Scoring must therefore use the primary taxonomy.
- On sampled pages: every record was active, had a phone, and had an authorized official with name and title. About 5 to 8 percent were subparts of a larger organization. About 10 percent listed extra practice locations.
- Almost no emails and no websites.
- Published rate limits are not confirmed. The connector waits 1 second between pages.

Individual records (`enumeration_type=NPI-1`), tested the same day on one 200-record page for Internal Medicine in Texas:

- 34 of 200 (17 percent) had `sole_proprietor = YES`. All 200 were active and had a location phone.
- The flag is self-reported. At least one flagged doctor listed a large academic medical center as the practice address, so the flag is a hint of a solo practice, not proof.
- The cap applies before our filter: 1,200 individual records yield roughly 200 sole proprietors per query. City narrows it further.

Consequence of the cap: the same state and specialty always returns the same first 1,200 records. The optional city field is how the operator reaches further into a large state. Automatic splitting is deferred.

## 4. Architecture

```text
Browser (localhost:3000)
  Next.js + TypeScript + Tailwind + shadcn/ui
        |  HTTP/JSON
        v
FastAPI (127.0.0.1:8000)
  api/        routes, Pydantic schemas
  services/   search, scoring, export
  sources/    npi_registry connector
  worker      one background thread, started with the app
        |  SQLAlchemy + psycopg
        v
Supabase PostgreSQL (hosted)
```

Units and their one job:

| Unit | Does | Depends on |
|---|---|---|
| `sources/npi_registry.py` | Fetches one page for a query, maps each raw record to a normalized lead dict. No database access. | httpx |
| `services/scoring.py` | Pure function: normalized lead plus scoring config in, components, total, priority, and reasons out. | scoring config |
| `services/search.py` | Runs one job: loop pages, upsert, score, update counters and checkpoint. | connector, scoring, database |
| `worker.py` | One daemon thread. Picks the oldest `queued` job, runs it, repeats. | search service |
| `services/export.py` | Filters in, `.xlsx` bytes out. | database, OpenPyXL |
| `api/` | HTTP layer only: validate, call a service, shape the response. | services |
| Frontend | Two pages: Search and Leads. | API |

No Redis, no Celery, no separate worker process. One search runs at a time; others wait in `queued`.

Database connection: use the Supabase session pooler connection string. The direct connection is IPv6-only on the free plan and often fails from home networks.

## 5. Data model

Eight tables. All have UUID primary keys, `created_at`, and `updated_at`. Created by Alembic migrations.

**`source_configs`**: `key` (unique, for example `npi_registry`), `name`, `status` (`available`, `approved_not_built`, `not_reviewed`, `rejected`), `access_method`, `rate_limit_per_sec`, `policy_reviewed_on`, `notes`. Seeded from `docs/data-sources.md`: NPI Registry as `available`, the 30 directories and the others with their documented status.

**`search_jobs`**: `specialty`, `state` (2-letter, checked), `city` (nullable), `target_count` (1 to 1200), `include_practices` (bool), `include_solo` (bool), `include_subparts` (bool), `include_hospitals` (bool), `sources` (text array), `status` (`queued`, `running`, `paused`, `completed`, `cancelled`, `failed`), `cancel_requested` (bool), `checkpoint` (JSONB: current phase, `practices` or `solo`, and next `skip` value), `counters` (JSONB), `error` (text), `started_at`, `finished_at`.

**`organizations`**: `npi` (text, unique), `name`, `dba_name`, `organization_type` (`practice`, `subpart`, `hospital`, `solo_provider`), `parent_organization_name`, `primary_taxonomy_code`, `primary_taxonomy_desc`, `phone`, `fax`, `state`, `city` (copied from the primary location for fast filtering), `fit_score` (int), `priority` (`critical`, `high`, `medium`, `low`), `crm_status` (the ten PRD statuses, default `new`), `status_updated_at`.

**`locations`**: `organization_id`, `purpose` (`location`, `mailing`, `practice`), `address_1`, `address_2`, `city`, `state`, `zip`, `phone`, `is_primary`. Unique on organization plus purpose plus address.

**`contacts`**: `organization_id`, `first_name`, `last_name`, `title`, `phone`, `role` (`authorized_official` for practices, `provider` for solo doctors), `source_key`. Unique on organization plus role plus name. Email columns arrive in slice 3.

**`source_records`**: `organization_id`, `source_key`, `external_id` (the NPI), `raw` (JSONB, the untouched API record), `collected_at`. Unique on source plus external id. This is the provenance record and lets leads be re-scored without calling the API again.

**`search_job_leads`**: `search_job_id`, `organization_id`, `was_new` (bool). Unique on the pair.

**`lead_scores`**: `organization_id` (unique, one current row per organization), `components` (JSONB: points and reason per factor), `total`, `priority`, `config_version`, `calculated_at`.

Indexes: `organizations` on `state`, `primary_taxonomy_desc`, `priority`, `fit_score`, `crm_status`, and `npi`; `search_job_leads` on both foreign keys.

Organization type rule: primary taxonomy code starting with `28` (hospitals) gives `hospital`; otherwise `organizational_subpart = YES` gives `subpart`; otherwise `practice`. The API cannot tell a small group from a large one, so both are `practice` in this slice.

Solo doctors: an individual record with `sole_proprietor = YES` is stored in `organizations` with type `solo_provider`. Its name is the doctor's name and credential (for example "Jane Smith, MD"), its NPI is the individual NPI, and the doctor is also saved as its contact with role `provider`. Individual records without the flag are never stored: most of them are employed doctors, not practices (PRD FR-03).

## 6. Search flow

1. `POST /api/search` validates input, refuses any source that is not `available`, inserts the job as `queued`, and returns it.
2. The worker thread picks it up and sets `running`.
3. The job runs up to two phases in order, each only if its toggle is on: `practices` (NPI-2 records), then `solo` (NPI-1 records) for whatever part of the target is still unfilled. For each page of the current phase (200 records, starting at the checkpoint's `skip`):
   - Fetch from the API. Retry transient failures up to 3 times with backoff.
   - For each record: skip if not active; skip if excluded by the inclusion toggles; in the solo phase, skip if `sole_proprietor` is not YES, and skip if the doctor's location phone equals the phone of an organization already stored (the doctor most likely works there); map to a normalized lead; upsert the organization by NPI; replace its locations; upsert the contact and source record; score it; link it to the job with `was_new`.
   - Commit the page's rows, the updated counters, and the new checkpoint in one transaction.
   - Stop the job if the target is reached or `cancel_requested` is set. Move to the next phase if the page had fewer than 200 records or `skip` would pass 1000.
   - Wait 1 second.
4. Final status: `completed`, or `cancelled`, or `failed` with the error text.

Restart safety: when the backend starts, any job still marked `running` is set to `paused`. `POST /api/search/{id}/resume` sets `paused` or `failed` jobs back to `queued`, and the worker continues from the checkpoint. Because every write is an upsert keyed on NPI, re-processing a page creates no duplicates.

Target counting: the target counts organizations linked to this job, whether new or already known from an earlier search. The counters show both numbers separately.

Counters: `candidates_seen`, `accepted_new`, `accepted_existing`, `skipped_excluded`, `skipped_inactive`, `skipped_not_sole_proprietor`, `skipped_works_at_known_org`, `pages_fetched`, `source_failures`.

If the API is exhausted before the target, the job completes with fewer leads and says so. It never pads.

Because practices fill the target first, a large-state search may never reach the solo phase. To get solo doctors specifically, untick Practices.

Limitation: the sole-proprietor flag is self-reported, so some solo leads will turn out to be employed doctors. The phone-match check removes only those whose employer is already in the database.

## 7. Scoring

Config lives in one versioned file, `backend/scoring_config.json`: weights, per-taxonomy points, title keywords, priority thresholds, and a `version` string. Changing it and running the re-score command updates every lead from its stored raw record.

Version 1 rules, total 100 (PRD FR-08 weights):

| Factor | Max | Rule |
|---|---|---|
| Specialty relevance | 25 | Primary taxonomy is core (Internal Medicine, Family Medicine, Geriatric Medicine, General Practice): 25. A subspecialty of those: 15. Anything else: 5. |
| Practice size and independence | 20 | `practice`: 20. `solo_provider`: 16, with the reason "self-reported sole proprietor". `subpart`: 8. `hospital`: 4. Size is unknown in this slice and the reason text says so. |
| Fit with ZCS services | 20 | Core primary-care taxonomies (Care Management fits): 20. Other outpatient specialties (RCM and staffing fit): 12. Hospitals: 5. |
| Business contactability | 10 | Practice phone present: 10. |
| Decision-maker reachable | 15 | Official or titled staff with name and title: 6, plus 9 only when a direct way to reach them exists (official's phone differs from the office phone, or any contact email found; staff need an email). Name only: 3. None: 0. A solo doctor is their own decision-maker: 10. The office line alone earns no reachability points (scoring config v4). |
| Multiple providers or locations | 10 | More than one practice location listed: 10. Otherwise 0, with the reason "provider count not available from this source". |

Priority thresholds (configurable): Critical 80 and above, High 65 to 79, Medium 45 to 64, Low below 45.

Missing data never earns points. The `disqualified` tier and conversion probability are not produced in this slice; nothing in the UI or export shows a conversion percentage.

These point values are a first guess to be tuned after the first real searches. That tuning is a config change, not a code change.

## 8. API

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | App and database check |
| GET | `/api/sources` | All sources with status, for the search form |
| POST | `/api/search` | Create and queue a job |
| GET | `/api/search` | Recent jobs, newest first |
| GET | `/api/search/{id}` | One job with status and counters |
| POST | `/api/search/{id}/cancel` | Request cancellation (honoured between pages) |
| POST | `/api/search/{id}/resume` | Re-queue a paused or failed job |
| GET | `/api/leads` | Paginated list. Filters: `q` (name, city, NPI), `state`, `specialty`, `organization_type`, `priority`, `min_score`, `crm_status`, `search_job_id`. Sort: score, name, updated. Each row includes the primary contact and score breakdown. |
| PATCH | `/api/leads/{id}` | Update `crm_status` only |
| POST | `/api/exports/excel` | Body is either the same filters as the list or a list of ids. Returns the workbook. |

The export route is POST, not GET as sketched in the PRD, because a list of selected ids does not fit in a URL.

Errors use one shape: `{ "error": { "code", "message" } }`. CORS allows only `http://localhost:3000`.

Re-scoring is a command, not an endpoint: `python -m app.rescore`.

## 9. Frontend

Two pages and a shared shell with a two-item nav.

**Search (`/search`)**
- Form: specialty (dropdown of configured specialties, with free text allowed), state (dropdown of 50 states plus DC), city (optional), target count (default 500, max 1200), checkboxes for lead types, "Practices" and "Solo doctors" (both on by default, at least one required), toggles for "include hospital and health-system subparts" and "include hospitals", and the Sources list.
- Sources list: every source from `/api/sources`. `available` ones have a checkbox. Others are greyed out with their status label.
- Jobs list below the form: status, progress bar against target, the counters, and Cancel or Resume. Polls every 2 seconds while any job is queued or running.
- A note under the target field explains the 1,200 cap and suggests using City for large states.

**Leads (`/leads`)**
- Server-driven table using the shadcn Table: organization, specialty, city and state, phone, primary contact and title, score, priority badge, sales status (inline dropdown), updated.
- Filter bar matching the API filters, a search box, sortable score and name columns, pagination.
- Clicking a row expands it to show the score breakdown with reasons, all locations, the source name, and the collection time.
- Row checkboxes and an Export button: exports the selection if any rows are ticked, otherwise the current filter.

Empty, loading, and error states on both pages. No dashboard, pipeline, or lead detail page in this slice.

## 10. Excel export

Three sheets, built from the database at export time:

1. **All Leads**: Organization Name, DBA Name, Specialty, Organization Type, Parent Organization, Business Phone, Fax, Contact Person, Contact Title, Contact Phone, Address, City, State, ZIP, NPI, Lead Score, Lead Priority, Outreach Status, Source, Collected On.
2. **Contacts**: one row per contact with organization name and NPI.
3. **Summary**: export time, filters used, lead counts by priority, by status, and by state.

Formatting: frozen header row, header filters, sensible column widths, date format, and color fills for priority and status. No email, website, or conversion columns, because this slice has no such data. The Activity History sheet arrives with slice 2.

## 11. Error handling

- API timeouts and 5xx responses: retried 3 times with backoff, then the job is `failed` with the message and can be resumed.
- A single malformed record: logged with the NPI, counted in `source_failures`, and skipped. The job continues.
- Database unavailable: `/health` reports it; the running job fails and is resumable.
- Invalid search input: rejected with a 422 and a field-level message.
- Logs carry the job id and never include the database URL.

## 12. Configuration

`.env` (backend only, git-ignored), with a committed `.env.example`:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres
FRONTEND_ORIGIN=http://localhost:3000
EXPORT_DIR=./exports
NPI_PAGE_DELAY_SECONDS=1
MAX_SOURCE_RETRIES=3
LOG_LEVEL=INFO
```

The frontend has one variable, `NEXT_PUBLIC_API_URL`. No Supabase key is used anywhere in the frontend.

## 13. Testing

- **Connector mapping**: recorded real API pages as JSON fixtures; assert the normalized output, including subparts, hospitals, and missing fields.
- **Scoring**: table-driven tests for each factor and each priority boundary, and that missing data scores zero.
- **Search job**: fake connector serving fixture pages; assert counters, target stop, cancel between pages, resume from checkpoint, and no duplicates when a page is replayed.
- **Export**: build a workbook from seeded rows and assert sheets, headers, and a few cell values.
- **API**: validation, the refusal of non-available sources, and list filters.

Pure-logic tests need no database. Database tests run against an embedded PostgreSQL started by the `pgserver` package (no Docker, no hosted database), or against `TEST_DATABASE_URL` when set. Tests never touch the real database. The frontend is checked by type-check, lint, and a manual walkthrough of the acceptance list.

## 14. Acceptance criteria

1. A search for one specialty and state creates a job row before any fetching starts.
2. Progress and counters update on the Search page while the job runs.
3. Stopping the backend mid-search and restarting leaves the job `paused`; Resume finishes it with no duplicate organizations.
4. Running the same search twice creates no duplicates; the second job reports existing leads separately.
5. With Solo doctors ticked, solo leads appear with type Solo provider, and no stored individual record lacks the sole-proprietor flag.
6. A greyed-out source cannot be selected, and a hand-crafted request naming it is refused.
7. Every lead shows a score, a priority, and a reason for each factor.
8. The leads table filters by state, specialty, priority, minimum score, and status, and paginates.
9. Changing a lead's status persists and appears in the next export.
10. The exported workbook opens in Excel with state, priority, score, and outreach status present.
11. Every organization has a source record with its collection time.
12. No conversion percentage appears anywhere.
13. No secret is committed, and no Supabase key exists in frontend code.
