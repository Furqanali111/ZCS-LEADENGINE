# Slice 1: Lead Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local app where the operator searches U.S. practices and solo doctors by specialty and state through the CMS NPI Registry API, sees them scored in a table, sets a sales status, and exports to Excel.

**Architecture:** Next.js frontend on `localhost:3000` calls a FastAPI backend on `127.0.0.1:8000`, which stores everything in Supabase PostgreSQL through SQLAlchemy. One background thread inside the backend runs search jobs page by page and checkpoints each page in the same transaction as its rows.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, psycopg 3, pydantic-settings, httpx, OpenPyXL, Pytest. Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-11-11-lead-discovery-design.md`. Read it and `CLAUDE.md` before any task.

## Global Constraints

- Zero PHI. Business data only.
- No code fetches from a source whose `source_configs.status` is not `available`.
- Never invent or pad data. Missing data scores zero.
- No conversion percentage anywhere in the UI, API, or export.
- Secrets live only in `backend/.env`. No Supabase key in frontend code. `.env`, `data/`, `exports/`, logs stay out of Git.
- NPI and phone are strings. Phones are stored as digits only (`"903-614-8500"` becomes `"9036148500"`).
- State is a two-letter code from the 50 states plus `DC`.
- NPI Registry API: page size 200, never request `skip` above 1000, wait `NPI_PAGE_DELAY_SECONDS` (default 1) between pages, retry a failed page at most `MAX_SOURCE_RETRIES` (default 3) times.
- Dependencies allowed in this slice are only those in Tech Stack. No pandas, Scrapy, Celery, Redis, tenacity, TanStack.
- No em dashes in code, comments, docs, or commit messages.
- Commits: one-line Conventional Commits subject, no body. Work on `feature/lead-discovery`, cut from `develop`. Never push to `develop`. Run `ponytail:ponytail-review` on the diff before opening the PR.
- UI tasks: invoke `21st:21st-ui` before writing markup, `impeccable:impeccable` for the finished screen, `design:accessibility-review` before finishing.
- Migrations: invoke `supabase:supabase-postgres-best-practices` first.

## Review Focus

1. The API silently repeats the last page when `skip` exceeds 1000. The job must end a phase after `skip=1000` and never loop. (Task 5)
2. Records with missing parts: no LOCATION address, no taxonomies, no authorized official, no phone. Mapping must not crash and scoring must give zero for the missing part. (Tasks 3, 4)
3. Phone formats differ inside one record (`903-614-8500` vs `9036142003`). Comparisons for "direct phone differs" and "works at a known organization" must use digits only. (Tasks 3, 5)
4. Names or addresses beginning with `=`, `+`, `-`, or `@` must reach Excel as text, not formulas. (Task 8)
5. A free-text specialty or city with spaces, ampersands, or no matches must be URL-encoded correctly and end as a completed job with zero leads, not a failed job. (Tasks 3, 5)

## Prerequisites (owner actions, before Task 1)

- [ ] Create a Supabase project. Copy the **session pooler** connection string.
- [ ] Provide an empty second Postgres database for tests (a second Supabase project or local Postgres). Its URL is `TEST_DATABASE_URL`. It must never be the real database.
- [ ] Approve an initial commit of the current docs on `main`, create `develop` from it, and push both. Then `feature/lead-discovery` is cut from `develop`.
- [ ] Python 3.12+ and Node 20+ installed.

## File Structure

```text
backend/
  pyproject.toml              deps, pytest config
  .env.example
  scoring_config.json         all scoring points and thresholds, versioned
  alembic.ini, migrations/    schema and source seed
  app/
    main.py                   app factory, CORS, error shape, lifespan (pause jobs, start worker)
    config.py                 Settings from .env
    db.py                     engine, SessionLocal, get_session
    models.py                 the eight tables
    constants.py              US_STATES, CRM_STATUSES, JOB_STATUSES, ORG_TYPES, PRIORITIES
    schemas.py                Pydantic request and response models
    sources/npi_registry.py   fetch_page, normalize, NormalizedLead
    services/scoring.py       load_config, score
    services/search.py        run_job, pause_running_jobs
    services/leads.py         LeadFilters, lead_query, save_score
    services/export.py        build_workbook
    worker.py                 start_worker
    rescore.py                python -m app.rescore
    api/health.py, sources.py, search.py, leads.py, exports.py
  tests/
    conftest.py               db fixture (skips without TEST_DATABASE_URL), client fixture
    fixtures/npi2_page.json, npi1_page.json   real recorded API pages, trimmed to 20 records each
    test_npi_registry.py, test_scoring.py, test_search.py, test_api.py, test_export.py
frontend/
  app/layout.tsx              shell with nav: Search, Leads
  app/page.tsx                redirect to /search
  app/search/page.tsx
  app/leads/page.tsx
  lib/api.ts                  typed fetch wrappers and shared types
  lib/constants.ts            US_STATES, SPECIALTIES, CRM_STATUSES with labels
  components/                 search-form, job-list, leads-table, lead-row-detail, lead-filters
README.md                     Windows setup and run commands
.gitignore
```

---

### Task 1: Backend skeleton, config, database connection, health

**Files:**
- Create: `.gitignore`, `backend/pyproject.toml`, `backend/.env.example`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/app/constants.py`, `backend/app/api/health.py`, `backend/tests/conftest.py`, `backend/tests/test_api.py`

**Interfaces:**
- Produces:
  - `config.get_settings() -> Settings` with fields `database_url: str`, `test_database_url: str | None`, `frontend_origin: str = "http://localhost:3000"`, `export_dir: str = "./exports"`, `npi_page_delay_seconds: float = 1`, `max_source_retries: int = 3`, `log_level: str = "INFO"`
  - `db.SessionLocal` (sessionmaker), `db.get_session()` FastAPI dependency
  - `main.create_app() -> FastAPI`
  - `constants.US_STATES: frozenset[str]` (50 states plus DC), `CRM_STATUSES = ("new","researching","email_sent","called","follow_up_required","interested","meeting_scheduled","not_interested","converted","do_not_contact")`, `JOB_STATUSES = ("queued","running","paused","completed","cancelled","failed")`, `ORG_TYPES = ("practice","subpart","hospital","solo_provider")`, `PRIORITIES = ("critical","high","medium","low")`
  - Test fixtures `db` (a Session on `TEST_DATABASE_URL`; creates all tables before and drops after each test; skips when unset; fails loudly if it equals `DATABASE_URL`) and `client` (TestClient with `get_session` overridden to `db`)
  - Error shape for every non-2xx: `{"error": {"code": str, "message": str}}`

- [ ] **Step 1:** Write `.gitignore` (`.env`, `data/`, `exports/`, `*.log`, `__pycache__/`, `.venv/`, `node_modules/`, `.next/`) and `backend/.env.example` with the six variables from spec section 12 plus `TEST_DATABASE_URL=`.
- [ ] **Step 2:** Write the failing tests in `tests/test_api.py`:

```python
def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}

def test_unknown_route_uses_error_shape(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert set(r.json()["error"]) == {"code", "message"}

def test_cors_allows_only_frontend_origin(client):
    r = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers
```

- [ ] **Step 3:** Run `cd backend && pytest -q`. Expected: fails on import.
- [ ] **Step 4:** Implement the files. `/health` runs `SELECT 1`; on failure it returns 503 with `{"status":"degraded","database":"error"}`. Logging never prints `database_url`.
- [ ] **Step 5:** Run `pytest -q`. Expected: 3 passed (or skipped if `TEST_DATABASE_URL` is unset; set it).
- [ ] **Step 6:** Run `uvicorn app.main:create_app --factory --port 8000` and open `http://127.0.0.1:8000/health`. Expected: `{"status":"ok","database":"ok"}` against the real Supabase database.
- [ ] **Step 7:** Commit: `feat(backend): add fastapi skeleton with health check`

### Task 2: Models, migration, source seed

**Files:**
- Create: `backend/app/models.py`, `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/0001_initial.py`, `backend/migrations/versions/0002_seed_sources.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `db`, `constants`
- Produces: ORM classes `SourceConfig`, `SearchJob`, `Organization`, `Location`, `Contact`, `SourceRecord`, `SearchJobLead`, `LeadScore`, with exactly the columns, unique constraints, and indexes in spec section 5. Status and type columns are text with CHECK constraints built from `constants`. `Organization.state` has a CHECK against `US_STATES`. `SearchJob.counters` defaults to `{}` and `SearchJob.checkpoint` to `{"phase": None, "skip": 0}`. Relationships: `Organization.locations`, `.contacts`, `.score` (one-to-one), all cascade delete.

- [ ] **Step 1:** Write failing tests:

```python
def test_duplicate_npi_rejected(db):  # IntegrityError on second insert of same npi
def test_invalid_state_rejected(db):  # state="ZZ" raises IntegrityError
def test_invalid_crm_status_rejected(db):  # crm_status="maybe" raises IntegrityError
def test_new_org_defaults(db):  # crm_status == "new", fit_score is None
def test_deleting_org_removes_children(db):  # locations, contacts, score, source_records gone
```

- [ ] **Step 2:** Run `pytest tests/test_models.py -q`. Expected: fail.
- [ ] **Step 3:** Implement `models.py`, then `alembic revision --autogenerate` for `0001_initial` and review it by hand against spec section 5.
- [ ] **Step 4:** Write `0002_seed_sources.py`: insert one row per source in `docs/data-sources.md`. `npi_registry` gets status `available`, `rate_limit_per_sec=1`, `policy_reviewed_on=2026-11-11`. `nppes_bulk` gets `approved_not_built`. `practice_websites` and the 30 directories get `not_reviewed`. Keys are lowercase snake case of the name (`yellow_pages`, `better_business_bureau`).
- [ ] **Step 5:** Run `pytest tests/test_models.py -q` (expect 5 passed), then `alembic upgrade head` against the real database, then `alembic downgrade base && alembic upgrade head` to prove a clean create.
- [ ] **Step 6:** Commit: `feat(db): add lead discovery schema and source seed`

### Task 3: NPI Registry connector

**Files:**
- Create: `backend/app/sources/npi_registry.py`, `backend/tests/fixtures/npi2_page.json`, `backend/tests/fixtures/npi1_page.json`
- Test: `backend/tests/test_npi_registry.py`

**Interfaces:**
- Produces:

```python
API_URL = "https://npiregistry.cms.hhs.gov/api/"
PAGE_SIZE = 200
MAX_SKIP = 1000

@dataclass
class NormalizedLead:
    npi: str
    name: str
    dba_name: str | None
    organization_type: str            # one of ORG_TYPES
    parent_organization_name: str | None
    primary_taxonomy_code: str | None
    primary_taxonomy_desc: str | None
    phone: str | None                 # digits only, from the LOCATION address
    fax: str | None
    city: str | None
    state: str | None
    locations: list[dict]             # keys: purpose, address_1, address_2, city, state, zip, phone, is_primary
    contact: dict | None              # keys: first_name, last_name, title, phone, role
    practice_location_count: int      # len(raw["practiceLocations"])
    active: bool                      # basic.status == "A"
    sole_proprietor: bool             # basic.sole_proprietor == "YES"; False for NPI-2
    raw: dict

def digits(phone: str | None) -> str | None            # strips non-digits; None if empty
def fetch_page(client: httpx.Client, *, enumeration_type: str, specialty: str,
               state: str, city: str | None, skip: int) -> list[dict]
def normalize(raw: dict) -> NormalizedLead
```

- `fetch_page` sends `version=2.1`, `enumeration_type`, `taxonomy_description`, `state`, `city` (only if set), `limit=200`, `skip` through httpx `params` (never string-built). It raises `ValueError` if `skip > MAX_SKIP`, raises `SourceError` on a non-200 or a body with `Errors`, and returns `[]` when `results` is missing or empty.
- `normalize` rules: `organization_type` is `solo_provider` for `enumeration_type == "NPI-1"`; otherwise `hospital` if the primary taxonomy code starts with `28`; otherwise `subpart` if `organizational_subpart == "YES"`; otherwise `practice`. Primary taxonomy is the entry with `primary: true`, else the first, else `None`. `dba_name` is the `other_names` entry of type "Doing Business As". NPI-2 `name` is `organization_name`, contact is the authorized official with role `authorized_official`. NPI-1 `name` is `"First Last, CRED"` in title case with dots removed from the credential (credential omitted if absent), contact is the doctor with role `provider` and the location phone. `is_primary` is true for the LOCATION address. ZIP keeps the first 5 digits.

- [ ] **Step 1:** Record fixtures: save the first 20 results of one real NPI-2 and one real NPI-1 query (Internal Medicine, TX) to the two fixture files. Make sure the NPI-2 file contains at least one `organizational_subpart: "YES"` record and the NPI-1 file at least one sole proprietor; pick records accordingly.
- [ ] **Step 2:** Write failing tests:

```python
def test_digits(): assert digits("903-614-8500") == "9036148500"; assert digits("") is None
def test_normalize_org_maps_core_fields():      # from fixture: npi, name, phone digits, state, contact role
def test_normalize_subpart_sets_type_and_parent()
def test_normalize_hospital_by_taxonomy_prefix():  # synthetic record, code "282N00000X"
def test_normalize_individual_builds_name():    # "Queenie Ann Abad, MD"-style, type solo_provider, role provider
def test_normalize_sparse_record_does_not_crash():
    lead = normalize({"number": "1234567890", "enumeration_type": "NPI-2",
                      "basic": {"organization_name": "X", "status": "A"},
                      "addresses": [], "taxonomies": [], "other_names": [], "practiceLocations": []})
    assert lead.phone is None and lead.contact is None and lead.primary_taxonomy_code is None
    assert lead.organization_type == "practice" and lead.locations == []
def test_fetch_page_encodes_params():            # httpx.MockTransport; specialty "Obstetrics & Gynecology", city "San Antonio"; assert request.url.params values round-trip
def test_fetch_page_empty_results_returns_list(): # body {"result_count": 0, "results": []} -> []
def test_fetch_page_api_error_raises():          # body {"Errors": [...]} -> SourceError
def test_fetch_page_refuses_skip_over_1000():    # ValueError
```

- [ ] **Step 3:** Run `pytest tests/test_npi_registry.py -q`. Expected: fail.
- [ ] **Step 4:** Implement.
- [ ] **Step 5:** Run again. Expected: all pass.
- [ ] **Step 6:** Commit: `feat(sources): add npi registry connector`

### Task 4: Scoring

**Files:**
- Create: `backend/scoring_config.json`, `backend/app/services/scoring.py`
- Test: `backend/tests/test_scoring.py`

**Interfaces:**
- Consumes: `NormalizedLead`
- Produces:

```python
@dataclass
class ScoreResult:
    total: int
    priority: str                       # one of PRIORITIES
    components: dict[str, dict]         # factor key -> {"points": int, "max": int, "reason": str}
    config_version: str

def load_config(path: str = "scoring_config.json") -> dict
def score(lead: NormalizedLead, config: dict) -> ScoreResult
```

- Factor keys: `specialty`, `independence`, `service_fit`, `contactability`, `decision_maker`, `multi_location`.
- `scoring_config.json` (exact content):

```json
{
  "version": "1",
  "core_taxonomy_codes": ["207R00000X", "207Q00000X", "207QG0300X", "207RG0300X", "208D00000X"],
  "subspecialty_prefixes": ["207R", "207Q"],
  "hospital_prefix": "28",
  "points": {
    "specialty": {"core": 25, "subspecialty": 15, "other": 5},
    "independence": {"practice": 20, "solo_provider": 16, "subpart": 8, "hospital": 4},
    "service_fit": {"core": 20, "other": 12, "hospital": 5},
    "contactability": {"phone": 10, "direct_phone": 5},
    "decision_maker": {"name_and_title": 10, "name_only": 5, "solo_provider": 10},
    "multi_location": {"multiple": 10}
  },
  "max": {"specialty": 25, "independence": 20, "service_fit": 20, "contactability": 15, "decision_maker": 10, "multi_location": 10},
  "priority_thresholds": {"critical": 80, "high": 65, "medium": 45}
}
```

- Rules not obvious from the config: no primary taxonomy gives `specialty` 0 and `service_fit` 0. `direct_phone` applies only when the contact phone exists, differs from the practice phone (digits compared), and the type is not `solo_provider`. `multi_location` is earned when `practice_location_count >= 1`; otherwise 0 with reason `"provider count not available from this source"`. The `independence` reason for `solo_provider` is `"self-reported sole proprietor"`; for `practice` it ends with `"size unknown from this source"`. Every component has a non-empty reason.

- [ ] **Step 1:** Write failing table-driven tests:

```python
def test_core_independent_practice_full_contact():   # 25+20+20+15+10+0 = 90, "critical"
def test_subspecialty_subpart():                     # code "207RR0500X", subpart, phone, official w/ same phone: 15+8+12+10+10+0 = 55, "medium"
def test_hospital():                                 # code "282N00000X": 5+4+5+10+10+0 = 34, "low"
def test_solo_provider_core():                       # 25+16+20+10+10+0 = 81, "critical"
def test_multi_location_adds_ten()
def test_missing_everything_scores_independence_only():  # sparse lead from Task 3: total 20, "low", every reason non-empty
@pytest.mark.parametrize("total,priority", [(80,"critical"),(79,"high"),(65,"high"),(64,"medium"),(45,"medium"),(44,"low")])
def test_priority_boundaries(total, priority)        # via a helper priority_for(total, config)
def test_name_only_official_gets_five()
def test_max_points_sum_to_100():                    # sum(config["max"].values()) == 100
```

- [ ] **Step 2:** Run `pytest tests/test_scoring.py -q`. Expected: fail.
- [ ] **Step 3:** Implement `load_config`, `priority_for`, `score`.
- [ ] **Step 4:** Run again. Expected: all pass.
- [ ] **Step 5:** Commit: `feat(scoring): add versioned fit score and priority`

### Task 5: Search job runner and worker

**Files:**
- Create: `backend/app/services/search.py`, `backend/app/worker.py`, `backend/app/services/leads.py` (only `save_score` in this task)
- Modify: `backend/app/main.py` (lifespan: `pause_running_jobs`, then `start_worker`; worker is not started when `app.state.testing` is true)
- Test: `backend/tests/test_search.py`

**Interfaces:**
- Consumes: `fetch_page`, `normalize`, `MAX_SKIP`, `PAGE_SIZE`, `score`, `load_config`, models
- Produces:

```python
def save_score(session, org: Organization, result: ScoreResult) -> None
    # upserts lead_scores and copies total and priority onto org.fit_score, org.priority

def run_job(session_factory, job_id: UUID, *, fetch=fetch_page, sleep=time.sleep) -> None
def pause_running_jobs(session) -> int          # running -> paused, returns count
def start_worker(session_factory) -> threading.Thread   # daemon; every 2s runs the oldest queued job
```

- `run_job` behavior (spec section 6): sets `running` and `started_at`. Phases in order `practices` (`NPI-2`) then `solo` (`NPI-1`), each only if its toggle is on, starting from `job.checkpoint`. Per record: skip inactive (`skipped_inactive`); in `practices`, skip `subpart` unless `include_subparts` and `hospital` unless `include_hospitals` (`skipped_excluded`); in `solo`, skip unless `sole_proprietor` (`skipped_not_sole_proprietor`), then skip if `lead.phone` equals the `phone` of any stored organization whose type is not `solo_provider` (`skipped_works_at_known_org`). Otherwise upsert `Organization` by `npi` (never overwrite `crm_status`), replace its locations, upsert contact and `SourceRecord` (`source_key="npi_registry"`, `external_id=npi`), score, link through `SearchJobLead` with `was_new`, and count `accepted_new` or `accepted_existing`. A record that raises is rolled back alone (savepoint), logged with its NPI, and counted in `source_failures`.
- After each page, one commit writes the rows, `counters`, and `checkpoint = {"phase": ..., "skip": skip + 200}`. Then: target reached (`accepted_new + accepted_existing >= target_count`) gives `completed`; `cancel_requested` gives `cancelled`; a page shorter than 200 or a next `skip` above `MAX_SKIP` moves to the next phase with `skip` 0; no phase left gives `completed`. Otherwise `sleep(settings.npi_page_delay_seconds)` and continue. Processing stops mid-page as soon as the target is reached.
- A failed fetch is retried up to `max_source_retries` times with `sleep(2 ** attempt)`; after that the job is `failed` with `error` set and the checkpoint left at the failed page. `finished_at` is set on completed, cancelled, and failed.

- [ ] **Step 1:** Write failing tests using a fake `fetch` built from the Task 3 fixtures and `sleep=lambda s: None`:

```python
def test_job_saves_orgs_scores_and_links(db):          # one 20-record page: orgs, locations, contacts, source_records, lead_scores, search_job_leads exist; status completed
def test_target_stops_job(db):                         # target 5 -> exactly 5 links, completed
def test_replaying_a_page_creates_no_duplicates(db):   # run same job input twice -> org count unchanged, second job accepted_existing == first accepted_new
def test_rerun_keeps_crm_status(db):                   # set crm_status="called", rerun -> still "called"
def test_excluded_subparts_counted(db):                # include_subparts False -> no subpart orgs, skipped_excluded > 0
def test_solo_phase_keeps_only_sole_proprietors(db):   # include_practices False -> all orgs solo_provider, skipped_not_sole_proprietor > 0
def test_solo_skipped_when_phone_matches_known_org(db) # pre-insert a practice with the doctor's phone in a different format
def test_never_requests_skip_above_1000(db):           # fetch always returns 200 unique records, target 5000 -> skips requested == [0,200,400,600,800,1000] per phase, status completed
def test_cancel_between_pages(db):                     # fetch sets cancel_requested during page 1 -> one page fetched, status cancelled
def test_fetch_failure_fails_job_then_resume_completes(db):  # page 2 raises 4 times -> failed, checkpoint skip == 200; requeue and run with working fetch -> completed, no duplicates
def test_bad_record_is_skipped_not_fatal(db):          # one record missing "number" -> source_failures == 1, others saved
def test_zero_results_completes_empty(db):             # fetch returns [] -> completed, 0 links
def test_pause_running_jobs(db):                       # running job -> paused
```

- [ ] **Step 2:** Run `pytest tests/test_search.py -q`. Expected: fail.
- [ ] **Step 3:** Implement `save_score`, `run_job`, `pause_running_jobs`, `start_worker`, and the lifespan wiring. Use PostgreSQL `INSERT ... ON CONFLICT` for the upserts.
- [ ] **Step 4:** Run again. Expected: all pass.
- [ ] **Step 5:** Commit: `feat(search): add resumable search job runner and worker`

### Task 6: Sources and search API

**Files:**
- Create: `backend/app/schemas.py`, `backend/app/api/sources.py`, `backend/app/api/search.py`
- Modify: `backend/app/main.py` (include routers)
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces (Pydantic):

```python
class SourceOut:   key, name, status, notes
class SearchCreate: specialty: str (1..100 chars, stripped), state: str, city: str | None (max 100),
                    target_count: int = 500 (1..1200), include_practices: bool = True, include_solo: bool = True,
                    include_subparts: bool = True, include_hospitals: bool = False, sources: list[str] (min 1)
class JobOut:      id, specialty, state, city, target_count, include_practices, include_solo, include_subparts,
                   include_hospitals, sources, status, counters: dict, error, created_at, started_at, finished_at
```

- Routes: `GET /api/sources` (all rows, `available` first, then by name), `POST /api/search` (201, `JobOut`), `GET /api/search` (latest 50), `GET /api/search/{id}`, `POST /api/search/{id}/cancel` (sets `cancel_requested`; a `queued` job becomes `cancelled` at once), `POST /api/search/{id}/resume` (only from `paused` or `failed`; sets `queued`, clears `error` and `cancel_requested`).
- Validation: `state` uppercased and in `US_STATES`; at least one of `include_practices`, `include_solo`; every key in `sources` must exist with status `available`, else 422 with code `source_not_available`. Resume or cancel in a wrong state returns 409 with code `invalid_job_state`. Unknown id returns 404.

- [ ] **Step 1:** Write failing tests:

```python
def test_sources_list_available_first(client, db)
def test_create_search_queues_job(client, db):                 # 201, status "queued", row exists
def test_create_search_rejects_bad_state(client):              # "ZZ" -> 422
def test_create_search_rejects_target_over_1200(client)
def test_create_search_requires_a_lead_type(client):           # both toggles false -> 422
def test_create_search_refuses_unavailable_source(client, db): # sources=["yelp"] -> 422, code "source_not_available"
def test_cancel_queued_job(client, db):                        # -> "cancelled"
def test_resume_only_from_paused_or_failed(client, db):        # completed -> 409; paused -> "queued"
def test_get_unknown_job_404(client)
```

- [ ] **Step 2:** Run `pytest tests/test_api.py -q`. Expected: new tests fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run again. Expected: all pass.
- [ ] **Step 5:** Manual check against the real database: start the backend, `POST /api/search` with `{"specialty":"Internal Medicine","state":"TX","target_count":50,"sources":["npi_registry"]}`, poll `GET /api/search/{id}` until `completed`, confirm about 50 organizations in Supabase.
- [ ] **Step 6:** Commit: `feat(api): add sources and search job endpoints`

### Task 7: Leads API and re-score command

**Files:**
- Modify: `backend/app/services/leads.py`, `backend/app/schemas.py`, `backend/app/main.py`
- Create: `backend/app/api/leads.py`, `backend/app/rescore.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces:

```python
class LeadFilters:  q: str | None, state: str | None, specialty: str | None, organization_type: str | None,
                    priority: str | None, min_score: int | None, crm_status: str | None, search_job_id: UUID | None
def lead_query(filters: LeadFilters) -> Select[Organization]     # used by list and export
class LeadOut:      id, npi, name, dba_name, organization_type, parent_organization_name, primary_taxonomy_desc,
                    phone, fax, city, state, fit_score, priority, crm_status, updated_at,
                    contact: {first_name, last_name, title, phone, role} | None,
                    locations: list[{purpose, address_1, address_2, city, state, zip, phone, is_primary}],
                    score: {components: dict, config_version, calculated_at} | None,
                    source: {source_key, collected_at} | None
class LeadPage:     items: list[LeadOut], total: int, page: int, page_size: int
class LeadPatch:    crm_status: str      # must be in CRM_STATUSES; extra fields forbidden
```

- `GET /api/leads`: query params are the `LeadFilters` fields plus `page` (default 1), `page_size` (default 50, max 200), `sort` (`score`, `name`, `updated`; default `score`), `order` (`asc`, `desc`; default `desc`). `q` is a case-insensitive contains match on name, DBA name, city, and NPI. `specialty` is a case-insensitive contains match on `primary_taxonomy_desc`. Null scores sort last. Ties break on `id`. Children are loaded with `selectinload`, not per row.
- `PATCH /api/leads/{id}`: sets `crm_status` and `status_updated_at`, returns `LeadOut`.
- `python -m app.rescore`: for every organization, `normalize(source_record.raw)`, `score`, `save_score`; prints the count.

- [ ] **Step 1:** Write failing tests (seed 6 organizations through a small helper):

```python
def test_leads_default_sort_is_score_desc(client, db)
def test_leads_filters_combine(client, db):          # state + priority + min_score
def test_leads_q_matches_name_city_npi(client, db)
def test_leads_filter_by_search_job(client, db)
def test_leads_pagination_total(client, db):         # page_size=2 -> 2 items, total 6
def test_lead_includes_contact_score_source(client, db)
def test_patch_status_persists(client, db)
def test_patch_invalid_status_422(client, db)
def test_patch_rejects_other_fields(client, db):     # {"name": "x"} -> 422
def test_rescore_updates_all(db):                    # change config thresholds in a temp file -> priorities change
```

- [ ] **Step 2:** Run. Expected: fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: all pass.
- [ ] **Step 5:** Commit: `feat(api): add leads list, status update and rescore command`

### Task 8: Excel export

**Files:**
- Create: `backend/app/services/export.py`, `backend/app/api/exports.py`
- Modify: `backend/app/schemas.py`, `backend/app/main.py`
- Test: `backend/tests/test_export.py`

**Interfaces:**
- Consumes: `lead_query`, `LeadFilters`
- Produces:
  - `build_workbook(session, *, filters: LeadFilters | None, ids: list[UUID] | None) -> bytes`
  - `POST /api/exports/excel` with body `ExportRequest {filters: LeadFilters | None, ids: list[UUID] | None}`; `ids` wins when both are given; max 5000 ids. Response content type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, filename `zcs-leads-YYYYMMDD-HHMM.xlsx`.
- Sheets and columns exactly as spec section 10. `Outreach Status` and `Lead Priority` show human labels ("Email sent", "Critical"). `Address` is the primary location's `address_1` plus `address_2`. `Source` is "CMS NPI Registry".
- Formatting: header row bold and frozen (`freeze_panes = "A2"`), `auto_filter` over the data range, column width from the longest value capped at 50, `Collected On` as `yyyy-mm-dd`, a solid fill per priority and per status on those two columns.
- Every text cell is written with `data_type = "s"` so a value starting with `=`, `+`, `-`, or `@` stays text.

- [ ] **Step 1:** Write failing tests (load the bytes back with `openpyxl.load_workbook`):

```python
def test_workbook_has_three_sheets(db):               # ["All Leads", "Contacts", "Summary"]
def test_all_leads_headers_match_spec(db):            # exact ordered list of the 20 headers
def test_row_values(db):                              # name, state, score, priority label, status label for one seeded org
def test_ids_override_filters(db)
def test_filters_limit_rows(db):                      # state filter -> only that state
def test_formula_like_name_is_text(db):               # org named "=HYPERLINK(1)" -> cell.data_type == "s" and value unchanged
def test_header_frozen_and_filtered(db):              # ws.freeze_panes == "A2"; ws.auto_filter.ref set
def test_summary_counts(db):                          # counts by priority match seeded data
def test_no_conversion_column(db):                    # no header contains "conversion" or "probability"
def test_export_endpoint_returns_xlsx(client, db):    # 200 and content type
def test_empty_export_still_valid(db):                # zero leads -> headers only, opens fine
```

- [ ] **Step 2:** Run. Expected: fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: all pass. Then export from the real database and open the file in Excel by hand.
- [ ] **Step 5:** Commit: `feat(export): add excel export of filtered or selected leads`

### Task 9: Frontend shell and Search page

**Files:**
- Create: `frontend/` (via `npx create-next-app@latest frontend --ts --tailwind --app --eslint --no-src-dir`, then `npx shadcn@latest init`), `frontend/lib/api.ts`, `frontend/lib/constants.ts`, `frontend/app/layout.tsx`, `frontend/app/page.tsx`, `frontend/app/search/page.tsx`, `frontend/components/search-form.tsx`, `frontend/components/job-list.tsx`, `frontend/.env.example` (`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`)

**Interfaces:**
- Consumes: the Task 6 routes and shapes.
- Produces in `lib/api.ts`: types `Source`, `Job`, `SearchInput`, `Lead`, `LeadPage`, `LeadFilters` mirroring the backend schemas field for field, and functions `getSources()`, `createSearch(input)`, `listJobs()`, `cancelJob(id)`, `resumeJob(id)`, `listLeads(params)`, `patchLeadStatus(id, status)`, `exportLeads(body): Promise<Blob>`. Each throws `ApiError(code, message)` built from the backend error shape.
- `lib/constants.ts`: `US_STATES` (code and name), `SPECIALTIES = ["Internal Medicine", "Family Medicine", "Geriatric Medicine", "General Practice"]`, `CRM_STATUSES` and `PRIORITIES` with display labels, `SOURCE_STATUS_LABELS` (`approved_not_built`: "Approved, not built yet"; `not_reviewed`: "Not reviewed yet").

- [ ] **Step 1:** Scaffold, add shadcn components `button`, `input`, `select`, `checkbox`, `label`, `table`, `badge`, `progress`, and write `lib/api.ts` and `lib/constants.ts`.
- [ ] **Step 2:** Build the shell: nav with Search and Leads, `/` redirects to `/search`.
- [ ] **Step 3:** Build `search-form.tsx` per spec section 9: specialty as a text input with the four suggestions (datalist), state select, optional city, target count (default 500, min 1, max 1200) with the helper text "One search returns at most 1,200 records. For large states, add a city.", checkboxes Practices and Solo doctors (both on; submit disabled if both off), toggles "Include hospital and health-system subparts" (on) and "Include hospitals" (off), and the Sources list. `available` sources get a checkbox (`npi_registry` pre-ticked); others render disabled with their status label; `rejected` sources are not rendered. Field-level messages from 422 responses.
- [ ] **Step 4:** Build `job-list.tsx`: one row per job with search summary, status badge, progress bar (`accepted_new + accepted_existing` over `target_count`), the counters with plain labels, the error text if failed, Cancel for queued or running, Resume for paused or failed. Poll `listJobs()` every 2 seconds while any job is queued or running; stop otherwise. Empty state: "No searches yet."
- [ ] **Step 5:** Verify: `npm run lint && npx tsc --noEmit` pass. With the backend running, create a 50-lead search and watch it complete; stop the backend mid-search on a 600-lead search, restart, see `paused`, press Resume, see it complete.
- [ ] **Step 6:** Run `design:accessibility-review` on the page and apply findings.
- [ ] **Step 7:** Commit: `feat(frontend): add app shell and search page`

### Task 10: Leads page

**Files:**
- Create: `frontend/app/leads/page.tsx`, `frontend/components/leads-table.tsx`, `frontend/components/lead-filters.tsx`, `frontend/components/lead-row-detail.tsx`

**Interfaces:**
- Consumes: `listLeads`, `patchLeadStatus`, `exportLeads`, `listJobs` (for the search-job filter), constants.

- [ ] **Step 1:** Build `lead-filters.tsx`: search box (debounced 300 ms), state, specialty, organization type, priority, minimum score, status, search job. Filter state lives in the URL query string so a refresh keeps it.
- [ ] **Step 2:** Build `leads-table.tsx` with the columns in spec section 9, server-driven sort on score and name, pagination (50 per page) showing "x to y of total", a priority badge, and an inline status select that calls `patchLeadStatus` and reverts with a visible message on failure. Solo providers show a "Solo" tag next to the name. A lead with no score shows a dash.
- [ ] **Step 3:** Build `lead-row-detail.tsx`: click a row to expand. Shows each score factor as "label: points of max, reason", all locations, source name, and collection date.
- [ ] **Step 4:** Add row checkboxes, a select-page checkbox, and the Export button: label "Export selected (n)" when rows are ticked, otherwise "Export filtered (total)". It downloads the Blob as a file. Disabled when the total is zero.
- [ ] **Step 5:** Loading, empty ("No leads match these filters."), and error states.
- [ ] **Step 6:** Verify: `npm run lint && npx tsc --noEmit` pass. By hand: every filter narrows the list, status change survives a refresh, expanded row shows six factors with reasons, both export modes download a workbook that opens in Excel.
- [ ] **Step 7:** Run `impeccable:impeccable` and `design:accessibility-review` on the page and apply findings.
- [ ] **Step 8:** Commit: `feat(frontend): add leads table with filters, status and export`

### Task 11: README, acceptance walkthrough, PR

**Files:**
- Create: `README.md`
- Modify: `docs/data-sources.md` (set `npi_registry` to `available`), `docs/deferred-items.md` (remove anything this slice delivered)

- [ ] **Step 1:** Write `README.md`: prerequisites, Windows setup for backend (venv, `pip install -e .[dev]`, `.env`, `alembic upgrade head`) and frontend (`npm install`, `.env.local`), the two run commands, the test command, and `python -m app.rescore`.
- [ ] **Step 2:** Run the full backend suite: `cd backend && pytest -q`. Expected: all pass, none skipped.
- [ ] **Step 3:** Walk through all 13 acceptance criteria in spec section 14 against the real database and record pass or fail for each in the PR body. For criterion 13 run `git grep -iE "service_role|supabase.*key" -- frontend` (expect no matches) and `git ls-files | grep -E "\.env$"` (expect no output).
- [ ] **Step 4:** Run `ponytail:ponytail-review` and `engineering:code-review` on the branch diff and apply findings.
- [ ] **Step 5:** Commit: `docs: add setup guide and mark npi registry available`
- [ ] **Step 6:** Rebase on `develop`, push `feature/lead-discovery`, and open a PR to `develop` with the acceptance results. Do not merge it yourself.
