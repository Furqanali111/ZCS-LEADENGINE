# Slice 3 Automatic Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One search-page toggle runs NPI search, then automatically finds each lead's official website, public emails and named staff, accepting a fact only when an automatic check passes.

**Architecture:** Enrichment is one more phase of the existing search job and worker. Pure modules do the work (Brave client, polite page fetcher, HTML verification and extraction); one service ties them to the database lead by lead, committing after each lead so a job resumes without repeats. No new tables.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, httpx, Python stdlib (`html.parser`, `urllib.robotparser`), Pytest on embedded Postgres, Next.js.

**Spec:** `docs/superpowers/specs/2026-11-12-enrichment-design.md`

## Global Constraints

- Zero PHI. Business pages only.
- Sources are opt-in: no fetch unless the source is `available` in `source_configs` and `docs/data-sources.md`. Yelp is `rejected` and no code calls it.
- Never bypass robots.txt (honor `Crawl-delay`), logins, rate limits, CAPTCHAs. About one request per second per domain. User agent `ZCSLeadEngine/1.0 (internal prospecting tool)`.
- Never invent data: no email guessing, no pattern building, no obfuscation decoding. Email status is only `found_on_page`, and the word "verified" never appears next to an email.
- Brave Search Results (titles, snippets, ranks, result lists) are used in memory only and never stored. Only a website URL we fetched and verified is stored.
- `BRAVE_API_KEY` lives only in backend `.env` and `.env.example`, never in frontend code or Git.
- Conventional Commits, one-line subject, trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. No em dashes anywhere.
- No new dependency. Search route prefix is `/api/search` (the spec's `/api/searches` means this).
- Fit score, priority and conversion probability stay three separate things.
- Run tests from `backend/` with the venv active: `pytest -q`.

## Review Focus

1. Lead with no phone (`phone` is None): website can only be accepted by name plus city, and must not crash.
2. Brave returns no results, or results with non-http URLs (`javascript:`, `mailto:`, relative): lead ends `no_website_found`, job continues.
3. Malformed, huge or non-UTF-8 HTML, and non-HTML content types: no crash, page skipped and counted.
4. Look-alike emails: `logo@2x.png`, `name@domain.com.` with trailing punctuation, upper case, duplicates, `mailto:` with `?subject=`: only real addresses stored once, lower-cased.
5. Names with punctuation or suffixes ("Smith, John A., M.D., P.A."): matching handles them; a title with no name ("Office Manager") stores no person.
6. Job cancelled or process restarted mid-enrichment: finished leads are not redone, the rest continue on resume.

---

### Task 1: Schema, models, settings, source seeds

**Files:**
- Create: `backend/migrations/versions/0005_enrichment.py`
- Modify: `backend/app/models.py`, `backend/app/config.py`, `backend/app/constants.py`, `backend/.env.example`
- Test: `backend/tests/test_models.py`, `backend/tests/test_migrations.py`

**Interfaces:**
- Produces: `Organization.website: str|None`, `website_evidence: dict|None`, `enrichment_status: str` (values in `ENRICHMENT_STATUSES`), `enriched_at: datetime|None`; `Contact.email: str|None`, `email_status: str|None`, `source_url: str|None`, `collected_at: datetime|None`; `SearchJob.enrich: bool`; `constants.ENRICHMENT_STATUSES = ("not_run", "enriched", "no_website_found", "failed", "rejected_by_user")`; `models.CONTACT_ROLES` gains `staff`, `general`; `Settings.brave_api_key: str|None = None`, `Settings.enrich_page_delay_seconds: float = 1`.

- [ ] **Step 1: Write failing tests** in `test_models.py`: default `enrichment_status == "not_run"`; a status outside `ENRICHMENT_STATUSES` raises `IntegrityError`; a `Contact(role="staff", email=...)` and `role="general"` insert; `role="other"` raises; `email_status="verified"` raises (check allows only `found_on_page` or null). In `test_migrations.py`, follow the existing 0004 test: after `upgrade head`, the new columns exist and `source_configs` has `brave_search` with status `approved_not_built`, `practice_websites` `approved_not_built`, `yelp` `rejected`; `downgrade 0004` removes them.
- [ ] **Step 2: Run** `pytest tests/test_models.py tests/test_migrations.py -q`. Expected: FAIL (columns missing).
- [ ] **Step 3: Implement** the model columns and check constraints (`ck_organizations_enrichment_status`, `ck_contacts_email_status`, widened `ck_contacts_role`), `enrich` on `SearchJob` (default false), and settings. Write migration `0005` (revises `0004`) with matching DDL, the widened role check (drop and recreate), and an `UPDATE source_configs` for the three keys (reviewed on 2026-11-12, notes copied from spec section 3). Add `BRAVE_API_KEY=` and `ENRICH_PAGE_DELAY_SECONDS=1` to `.env.example`.
- [ ] **Step 4: Run** the same command. Expected: PASS, plus `pytest -q` stays green.
- [ ] **Step 5: Commit** `feat(enrichment): add enrichment columns and source records`.

### Task 2: Polite page fetcher

**Files:**
- Create: `backend/app/sources/web.py`
- Test: `backend/tests/test_web_fetcher.py`

**Interfaces:**
- Produces: `class FetchFailed(Exception)`; `@dataclass Page(url: str, html: str)`; `class PoliteFetcher` with `__init__(self, client: httpx.Client, *, sleep=time.sleep, clock=time.monotonic, min_interval: float = 1.0)`, `get(self, url: str) -> Page | None`, and `stats: dict` with int keys `pages_fetched`, `blocked_by_robots`, `skipped`.

- [ ] **Step 1: Write failing tests** with `httpx.MockTransport`: returns `Page` for HTML 200; `get` of a URL disallowed in robots.txt returns None and bumps `blocked_by_robots` without requesting the page; `Crawl-delay: 3` makes the injected `sleep` get called with at least 3 between two requests to one domain; two domains do not wait on each other; 403, 404, `Content-Type: application/pdf`, and a body over 1 MB return None and bump `skipped`; a CAPTCHA marker page (body containing "captcha" and under 5 KB) returns None and bumps `skipped`; 500 retries twice then raises `FetchFailed`; a timeout raises `FetchFailed`; robots.txt itself failing with 5xx is treated as allow-nothing (None, `blocked_by_robots`); robots.txt cached per domain (one request across three pages).
- [ ] **Step 2: Run** `pytest tests/test_web_fetcher.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `PoliteFetcher` using `urllib.robotparser.RobotFileParser.parse()` fed from the httpx response (not its own network call), per-domain last-request time for spacing (`max(min_interval, crawl_delay)`), `User-Agent` header, `follow_redirects` capped at 3, redirects to another registrable domain returned as the final `Page.url`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(enrichment): add robots-aware page fetcher`.

### Task 3: Brave search client

**Files:**
- Create: `backend/app/sources/brave.py`
- Test: `backend/tests/test_brave.py`

**Interfaces:**
- Produces: `class SearchError(Exception)` with attribute `kind: Literal["auth","rate_limited","failed"]`; `search(client: httpx.Client, api_key: str, query: str, count: int = 5) -> list[str]` returning result URLs only (nothing else is returned, so nothing else can be stored).

- [ ] **Step 1: Write failing tests** with `MockTransport`: sends `X-Subscription-Token` header and `q`, `count` params to `https://api.search.brave.com/res/v1/web/search`; returns the `web.results[].url` list; empty or missing `web` returns `[]`; 401/403 raises `SearchError(kind="auth")`; 429 raises `kind="rate_limited"`; 5xx and non-JSON raise `kind="failed"`; the api key never appears in the exception message.
- [ ] **Step 2: Run** `pytest tests/test_brave.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `search`. Add `Cache-Control: no-cache` header (best effort, per Brave docs).
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(enrichment): add Brave search client`.

### Task 4: Verification and extraction (pure)

**Files:**
- Create: `backend/app/services/verify.py`
- Test: `backend/tests/test_verify.py`, fixture pages in `backend/tests/fixtures/web/` (`practice_home.html`, `practice_contact.html`, `practice_team.html`, `aggregator.html`, `malformed.html`)

**Interfaces:**
- Produces (all pure, no I/O):
  - `BLOCKED_DOMAINS: frozenset[str]` (yelp, healthgrades, vitals, zocdoc, webmd, facebook, instagram, linkedin, twitter, x, youtube, yellowpages, manta, bbb, mapquest, npino, npiprofile, doximity, usnews, ratemds, wikipedia, any `.gov`).
  - `registrable_domain(host: str) -> str` (last two labels, `www.` dropped).
  - `candidate_roots(urls: list[str], limit: int = 3) -> list[str]`: http(s) only, blocklist removed, one root URL (`https://domain/`) per registrable domain, input order kept.
  - `page_text(html: str) -> str` (visible text, scripts and styles dropped, whitespace collapsed; never raises).
  - `page_links(html: str, base_url: str) -> list[tuple[str, str]]` (absolute href, link text).
  - `relevant_links(links, site_domain: str, limit: int = 4) -> list[str]`: same registrable domain only, link text or path containing contact, about, team, staff, provider, doctor, physician, our-team, leadership.
  - `verify_website(text: str, *, phones: list[str], name: str, city: str | None) -> str | None`: returns `"phone"` if any phone's 10 digits appear in the text's digits, else `"name_city"` if every distinctive word of the cleaned name (case-insensitive, punctuation and suffixes like PLLC, PA, P.A., LLC, INC, MD dropped, words under 3 chars ignored) and the city appear, else None. A name with no distinctive words never matches.
  - `@dataclass EmailHit(email: str, general: bool)`; `extract_emails(html: str, text: str, *, site_domain: str, phone_verified: bool) -> list[EmailHit]`: from `mailto:` hrefs (query string stripped) and plain text; lower-cased, trailing punctuation stripped, deduped; image-like or file-like endings (`.png .jpg .gif .svg .webp .pdf`) rejected; accepted only if the domain's registrable domain equals `site_domain`, or `phone_verified` is true; `general` when the local part is one of info, office, contact, admin, frontdesk, appointments, billing, hello, reception, scheduling, mail, support.
  - `@dataclass PersonHit(first_name: str, last_name: str, title: str)`; `extract_people(text: str) -> list[PersonHit]`: a two-or-three-word person name (an optional `Dr.`/`Mr.`/`Ms.` prefix and credential suffixes after a comma are stripped) within 60 characters of an allowlisted title (practice manager, office manager, administrator, owner, CEO, director, medical director, billing manager, MD, DO, NP, PA), deduped by name. A title with no name yields nothing.
- Consumes: nothing.

- [ ] **Step 1: Write failing tests**, one per behavior above, using the fixture pages and these named cases: `test_phone_match_any_formatting`, `test_name_city_match_with_suffixes`, `test_no_phone_lead_uses_name_city_only` (Review Focus 1), `test_aggregator_domain_dropped`, `test_non_http_urls_dropped` (2), `test_malformed_html_does_not_raise` and `test_bytes_garbage_text` (3), `test_email_lookalikes` (4: `logo@2x.png`, `A@B.com.`, `mailto:a@b.com?subject=x`, duplicates), `test_email_foreign_domain_needs_phone_verified`, `test_general_mailbox_flag`, `test_person_with_suffixes` (5: `"Smith, John A., M.D., P.A."` style text), `test_title_without_name_yields_nothing`.
- [ ] **Step 2: Run** `pytest tests/test_verify.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** with `html.parser.HTMLParser`, `re`, `urllib.parse`. No new dependency.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(enrichment): add website verification and extraction`.

### Task 5: Email suppression matching

**Files:**
- Modify: `backend/app/services/suppression.py`
- Test: `backend/tests/test_suppression.py`

**Interfaces:**
- Produces: `suppressed_emails(session: Session, emails: Collection[str]) -> set[str]` (lower-cased emails present in the list with kind `email`); `_matches()` and `add_entry` now also match leads that have a contact with that email.
- Consumes: `Contact.email` from Task 1.

- [ ] **Step 1: Write failing tests**: adding an email entry marks the lead with a contact of that email `do_not_contact` and logs a status change; adding it with no matching lead changes nothing; `suppressed_emails` returns only the listed ones, case-insensitively; `enforce` on a lead whose stored contact email is later suppressed sets `do_not_contact`; the existing test that says email entries match nothing is rewritten to the new behavior.
- [ ] **Step 2: Run** `pytest tests/test_suppression.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**: add an `exists()` over `Contact.email` in `_matches()`; in `add_entry` mark by `Organization.id.in_(select(Contact.organization_id).where(Contact.email == value))`; add `suppressed_emails`. Remove the now-false comment in `_matches`.
- [ ] **Step 4: Run** `pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(suppression): match stored contact emails`.

### Task 6: Enrichment service

**Files:**
- Create: `backend/app/services/enrich.py`
- Test: `backend/tests/test_enrich.py`

**Interfaces:**
- Consumes: `search(client, key, query) -> list[str]` shape from Task 3 (injected as `Callable[[str], list[str]]`), `PoliteFetcher.get` (injected as `Callable[[str], Page | None]` plus its `stats`), Task 4 functions, `suppressed_emails`, `SOURCE_KEY = "practice_website"`.
- Produces:
  - `enrich_lead(session: Session, org: Organization, *, search: Callable[[str], list[str]], fetch: Callable[[str], Page | None], counters: dict, now: Callable[[], datetime]) -> str` — enriches one lead, sets `website`, `website_evidence` (`{"page_url", "check", "checked_at"}`), `enrichment_status`, `enriched_at`, replaces that lead's `practice_website` contacts, rescores (Task 8 supplies the staff factor; call `save_score` as search.py does), and returns the status. Raises `SearchError` and `FetchFailed` upward.
  - `enrich_job_leads(session_factory, job_id: UUID, *, search, fetch, fetch_stats: dict, sleep) -> str` returning `"done"`, `"cancelled"` or `"paused"`; loops the job's `search_job_leads` whose org has `enrichment_status` in (`not_run`, `failed`), one transaction per lead, updates `job.counters`, checks `cancel_requested` between leads, maps `SearchError(auth)` to `paused` with `job.error` set, sleeps and retries once on `rate_limited`, counts `enrich_failures` and marks the lead `failed` on `FetchFailed` or `SearchError(failed)`.
- Counter keys (add to `COUNTERS` in Task 7): `enrich_attempted`, `websites_found`, `no_website_found`, `emails_found`, `people_found`, `pages_fetched`, `blocked_by_robots`, `enrich_failures`.

- [ ] **Step 1: Write failing tests** with a fake `search` and a dict-backed fake `fetch`: lead with phone on home page gets website, a `general` email and a `staff` person with source URL and `collected_at`, status `enriched`; no passing candidate gives `no_website_found` and no website or contacts; query sent is `"{name} {city} {state}"`; the second candidate is tried when the first fails verification; suppressed email is not stored; a rerun on the same lead replaces its web contacts without duplicates and keeps NPI contacts; `FetchFailed` marks `failed` and counts `enrich_failures`; `SearchError(auth)` returns `paused` with an error message that does not contain the key; cancel between leads returns `cancelled`; already-`enriched` leads are skipped (resume, Review Focus 6); `rejected_by_user` leads are skipped; stored data contains no search-result titles or snippets (assert `website_evidence` keys exactly).
- [ ] **Step 2: Run** `pytest tests/test_enrich.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** following spec section 6 steps 1 to 9: candidates via `candidate_roots`; verify home page; on accept fetch up to 4 `relevant_links`; `phone_verified` is true for a page where `verify_website` returned `"phone"`; emails stored via `insert(Contact)` with `role` `general` (email in `last_name`, per spec section 5) or attached to a `staff` person when the same page text places that email within 200 characters of the person's name; persons stored as `role="staff"`, `email_status` set only on rows with an email.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(enrichment): add per-lead enrichment service`.

### Task 7: Job integration and API validation

**Files:**
- Modify: `backend/app/services/search.py`, `backend/app/schemas.py`, `backend/app/api/search.py`, `backend/app/worker.py` (only if the signature needs it)
- Test: `backend/tests/test_search.py`, `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `enrich_job_leads` (Task 6), `Settings.brave_api_key`, `Settings.enrich_page_delay_seconds`.
- Produces: `SearchCreate.enrich: bool = False`; `JobOut.enrich: bool`; `run_job(session_factory, job_id, *, fetch=fetch_page, sleep=time.sleep, enrich_deps: EnrichDeps | None = None)` where `@dataclass EnrichDeps(search: Callable, fetch: Callable, fetch_stats: dict)` (tests inject fakes; default builds real clients from settings); `COUNTERS` extended with the Task 6 keys; checkpoint phase `"enrich"`.

- [ ] **Step 1: Write failing tests**: with `enrich` false nothing changes (existing tests stay green); with `enrich` true the job runs the NPI phases then enriches the linked leads and finishes `completed` with counters filled; a job resumed with checkpoint phase `enrich` skips NPI fetching entirely (`calls` empty) and enriches only `not_run` leads; auth error pauses the job with the message; cancel during enrichment ends `cancelled`; API: `POST /api/search` with `enrich: true` returns 422 `source_not_available` when `brave_search` or `practice_websites` is not `available`, and 422 `missing_api_key` when `BRAVE_API_KEY` is unset, and 201 otherwise; `JobOut` shows `enrich`.
- [ ] **Step 2: Run** `pytest tests/test_search.py tests/test_api.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**. In `run_job`, replace the two `_finish(session, job, "completed")` exits with a helper `_complete(session, job, counters, deps)` that, when `job.enrich`, sets `job.checkpoint = {"phase": "enrich"}`, commits, runs `enrich_job_leads`, merges `fetch_stats` into counters, and finishes with the returned status; at the top of `run_job`, a checkpoint phase of `"enrich"` goes straight to `_complete`. The enrich step also requires `brave_search` and `practice_websites` to be `available`, else `_finish(... "failed", "Source ... is not available")`. Keep the NPI check as is.
- [ ] **Step 4: Run** `pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(enrichment): run enrichment as a search job phase`.

### Task 8: Scoring factor and rescore

**Files:**
- Modify: `backend/app/services/scoring.py`, `backend/scoring_config.json`, `backend/app/rescore.py`, `backend/app/services/enrich.py`
- Test: `backend/tests/test_scoring.py`

**Interfaces:**
- Produces: `score(lead: NormalizedLead, config: dict, *, staff_with_title: bool = False) -> ScoreResult`; config key `points.decision_maker.staff_with_title: 10`; `version: "2"`.

- [ ] **Step 1: Write failing tests**: an organization record with no named official but `staff_with_title=True` gets 10 points with reason "named staff member with title found on practice website"; default call unchanged; version is `"2"`; `rescore_all` passes `staff_with_title=True` for a lead having a `staff` contact with a title.
- [ ] **Step 2: Run** `pytest tests/test_scoring.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**: staff branch placed after the solo branch and before the official branches only when no official has name and title; update `rescore_all` and `enrich_lead` to compute the flag from stored contacts. Bump config version.
- [ ] **Step 4: Run** `pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(scoring): count website staff as decision-maker`.

### Task 9: Lead API, reject website, export

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/api/leads.py`, `backend/app/services/leads.py`, `backend/app/services/export.py`
- Test: `backend/tests/test_api.py`, `backend/tests/test_export.py`

**Interfaces:**
- Produces: `ContactOut` gains `email`, `email_status`, `source_url`, `collected_at`; `LeadOut` gains `website`, `enrichment_status`, `primary_email`, `contacts: list[ContactOut]`, `website_evidence`; `LeadPatch.reject_website: bool | None`; `LeadFilters.has_website: bool | None`, `has_email: bool | None`; export headers add `Website`, `Email`, `Decision-maker` at the end of `HEADERS`.

- [ ] **Step 1: Write failing tests**: detail returns website, evidence and all contacts with source links; list returns `primary_email` (first `general` or staff email, else null); `PATCH {"reject_website": true}` clears `website` and `website_evidence`, deletes `practice_website` contacts, sets `rejected_by_user`, writes a `note` activity "Website rejected", keeps NPI contacts, and a later enrichment run skips the lead; `reject_website: false` is a 422; `has_website=true` and `has_email=true` filter; export has the three columns, Decision-maker reads `"Jane Doe, Practice Manager"`, and email cells never start a formula.
- [ ] **Step 2: Run** `pytest tests/test_api.py tests/test_export.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**. `LeadPatch.need_a_field` and the status validator must still work when only `reject_website` is sent.
- [ ] **Step 4: Run** `pytest -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(leads): expose website and emails, add reject website`.

### Task 10: Frontend

**Files:**
- Modify: `frontend/lib/api.ts`, `frontend/components/search-form.tsx`, `frontend/components/job-list.tsx`, `frontend/components/leads-table.tsx`, `frontend/components/lead-filters.tsx`, `frontend/app/leads/[id]/page.tsx`

**Interfaces:**
- Consumes: API fields from Tasks 7 and 9.

- [ ] **Step 1:** Add types to `lib/api.ts` (`enrich`, counters, lead and contact fields, `has_website`, `has_email`, `reject_website`).
- [ ] **Step 2:** Search form: checkbox "Also find websites and emails" (hint: uses your Brave key, one query per lead; shows the lead count as the expected query count); an API 422 `missing_api_key` or `source_not_available` is shown inline with its message.
- [ ] **Step 3:** Job list: counts for websites found, emails found, people found, no website, plus a paused-with-error message.
- [ ] **Step 4:** Leads table: Website (link, opens in a new tab with `rel="noopener noreferrer"`) and Email columns; filter checkboxes "Has website", "Has email".
- [ ] **Step 5:** Lead page: website link with evidence line ("phone matched on /contact"), "Not this website" button (confirm, then PATCH), contacts list showing email, "Found on page" label, source link and collection date. The word "verified" is not used for emails.
- [ ] **Step 6: Verify:** from `frontend/` run `npm run lint`, `npx tsc --noEmit`, `npm run build`. Expected: all pass. Run the `design:accessibility-review` skill on the lead page and search form and fix findings.
- [ ] **Step 7: Commit** `feat(enrichment): add enrichment toggle and lead website UI`.

### Task 11: Docs and live check

**Files:**
- Modify: `docs/data-sources.md`, `docs/deferred-items.md`, `README.md`, `docs/superpowers/specs/2026-11-12-enrichment-design.md`

- [ ] **Step 1:** `docs/data-sources.md`: record the section 3 review table, set statuses as in Task 1 (Brave and websites stay `approved_not_built` until the owner confirms Brave storage terms, then `available`), mark Yelp `rejected` with the reason and date.
- [ ] **Step 2:** `docs/deferred-items.md`: remove the website, email, decision-maker and email-suppression rows; add directories, cross-source dedup, solo flag, MX checks, JS-rendered pages as Slice 3 deferrals; add "Brave storage terms confirmation" and "pre-existing leads enrichment (leads from older searches)".
- [ ] **Step 3:** `README.md`: `BRAVE_API_KEY` setup, the toggle, and the rules. Spec: change the error code line from 400 to 422 and `/api/searches` to `/api/search` to match the code.
- [ ] **Step 4: Live check (needs the owner's key and Brave confirmation).** Set `BRAVE_API_KEY` in `backend/.env`, set the two sources `available` through the migration seed or a one-line SQL the owner approves, run a 10-lead search with the toggle, then report counts and spot-check 5 leads' website and emails against their pages. If the key or confirmation is missing, skip and say so.
- [ ] **Step 5:** Run `ponytail:ponytail-review` and `engineering:code-review` on the branch diff and apply findings. Commit `docs(enrichment): record source review and update docs`.
