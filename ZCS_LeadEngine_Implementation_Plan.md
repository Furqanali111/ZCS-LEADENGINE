# ZCS LeadEngine

## Implementation Plan

**Document status:** Engineering execution plan\
**Version:** 1.0\
**Prepared:** November 2026\
**Companion document:** `ZCS_LeadEngine_Architectural_PRD.md`

------------------------------------------------------------------------

## 1. Implementation strategy

Build ZCS LeadEngine in the four delivery slices defined in PRD section
15. Real leads come first: the first slice proves that the data is good
enough before the full CRM is built.

  Slice                      Phases from this document
  -------------------------- ------------------------------------------
  1 Lead discovery           0, 1, 3, 5, 9, plus the leads table from
                             Phase 2 and an NPI Registry API connector
                             in place of Phase 4
  2 CRM                      The rest of Phase 2
  3 Enrichment               6, 7, 8
  4 Conversion probability   The later model phase in Phase 3

Phases 10 and 11 (testing, security) apply to every slice. Phase 4, the
bulk NPPES importer, is deferred (see `docs/deferred-items.md`).

The phase numbers below are labels, not the build order. The slice table
above is the order.

------------------------------------------------------------------------

## 2. Architecture and repository structure

Recommended repository:

``` text
zcs-leadengine/
├── frontend/
│   ├── app/
│   │   ├── dashboard/
│   │   ├── search/
│   │   ├── leads/
│   │   ├── leads/[id]/
│   │   ├── pipeline/
│   │   └── exports/
│   ├── components/
│   ├── lib/
│   ├── hooks/
│   └── types/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   ├── database/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   │   ├── search_service.py
│   │   │   ├── nppes_service.py
│   │   │   ├── discovery_service.py
│   │   │   ├── enrichment_service.py
│   │   │   ├── deduplication_service.py
│   │   │   ├── scoring_service.py
│   │   │   ├── crm_service.py
│   │   │   └── export_service.py
│   │   ├── sources/
│   │   ├── workers/
│   │   └── utils/
│   ├── tests/
│   └── requirements.txt
├── migrations/
├── scripts/
│   ├── import_nppes.py
│   └── validate_environment.py
├── data/
│   └── nppes/                 # ignored by git; large local source files
├── exports/                   # ignored by git
├── docs/
├── .env.example
├── .gitignore
├── README.md
└── docker-compose.yml         # optional, not required for MVP
```

Keep downloaded source files, local database dumps, exports, secrets,
and logs out of version control.

------------------------------------------------------------------------

## 3. Phase 0: Project setup and engineering standards

### Tasks

-   Create the repository and folder structure.
-   Initialize Next.js with TypeScript.
-   Initialize FastAPI backend.
-   Add formatting, linting, and type-checking.
-   Add `.env.example` with placeholders only.
-   Add `.gitignore`.
-   Establish local frontend/backend startup commands.
-   Add health endpoint, such as `GET /health`.
-   Add structured logging and request IDs.
-   Document Windows development setup.

### Suggested frontend dependencies

-   Next.js
-   TypeScript
-   Tailwind CSS
-   shadcn/ui
-   TanStack Table for lead tables
-   TanStack Query or a consistent data-fetching approach
-   Zod for client-side schema validation where useful

### Suggested backend dependencies

-   fastapi
-   uvicorn
-   sqlalchemy
-   alembic
-   psycopg
-   pydantic-settings
-   pandas
-   openpyxl
-   beautifulsoup4
-   scrapy
-   dnspython
-   httpx
-   tenacity
-   pytest

Add Playwright only when a permitted source genuinely requires browser
rendering. Avoid installing unnecessary packages early.

### Exit criteria

-   Frontend starts locally.
-   Backend starts locally.
-   Frontend can call backend health endpoint.
-   No secrets are committed.
-   Setup instructions work on the target Windows machine.

------------------------------------------------------------------------

## 4. Phase 1: Supabase and database foundation

### Tasks

1.  Create a Supabase project.
2.  Configure backend-only database credentials.
3.  Choose the appropriate PostgreSQL connection method for local
    backend use.
4.  Add SQLAlchemy engine/session configuration.
5.  Initialize Alembic.
6.  Create initial migrations.
7.  Add database health check.
8.  Test create/read/update/delete operations in a development
    environment.
9.  Add database indexes and constraints.

### Initial tables

-   `search_jobs`
-   `organizations`
-   `locations`
-   `contacts`
-   `source_records`
-   `search_job_leads`
-   `lead_scores`
-   `lead_activities`
-   `email_verifications`
-   `suppression_list`
-   `source_configs`

### Schema rules

-   UUID primary keys.
-   NPI stored as string.
-   State stored as validated two-letter US code.
-   Unique constraints for reliable identifiers where appropriate.
-   Foreign keys and deletion behavior defined explicitly.
-   `created_at` and `updated_at` timestamps.
-   Index common filters: state, specialty, status, priority, score,
    NPI, normalized domain, and follow-up date.
-   Preserve historical activities and suppression entries.

### Exit criteria

-   Migrations can create a clean database.
-   Backend can connect and execute queries.
-   Database constraints reject invalid state codes and invalid status
    values.
-   Service-role key is never exposed to frontend code.

------------------------------------------------------------------------

## 5. Phase 2: Lead management and CRM before scraping

Use a small, clearly labeled sample dataset for this phase.

### Backend tasks

-   Organization CRUD.
-   Location CRUD.
-   Contact CRUD.
-   Lead list pagination, search, sorting, and filters.
-   Lead detail endpoint.
-   CRM status update.
-   Activity creation and retrieval.
-   Follow-up date handling.
-   Dashboard aggregation endpoints.

### Frontend tasks

Build the initial application shell:

1.  Dashboard
2.  All Leads
3.  Lead Details
4.  Pipeline
5.  Search
6.  Exports

Build the All Leads table with:

-   Organization
-   Specialty
-   City/state
-   Website
-   Phone
-   Primary contact
-   Lead score
-   Priority
-   CRM status
-   Next follow-up

Build lead detail view with:

-   Organization information
-   Locations
-   Contacts
-   Source records
-   Score explanation
-   Activity timeline
-   Notes and follow-up controls

Build pipeline Kanban using the agreed CRM statuses.

### Exit criteria

-   A user can create and edit a sample lead.
-   A user can add multiple contacts and locations.
-   Status updates appear in the table and pipeline.
-   Activity history remains intact after status changes.
-   Filters and pagination work against the database.

------------------------------------------------------------------------

## 6. Phase 3: Lead scoring and priority

Implement a deterministic, versioned scoring service.

### Initial scoring model

  Factor                             Weight
  -------------------------------- --------
  Specialty relevance                    25
  Practice size and independence         20
  ZCS service fit                        20
  Business contactability                15
  Decision-maker identified              10
  Multiple providers/locations           10
  Total                                 100

### Tasks

-   Define input features and normalization rules.
-   Implement component scoring functions.
-   Store each component score and its explanation.
-   Store scoring model version and calculation timestamp.
-   Map total score to configurable priority tiers.
-   Add a manual re-score action for testing.
-   Add tests for edge cases and missing data.
-   Show a score explanation in lead details and table tooltips.

### Important separation

-   Fit score measures how well the practice matches ZCS's target
    profile.
-   Priority helps decide what to contact first.
-   Conversion probability estimates the chance of a defined sales
    outcome.

Do not display a 75/100 fit score as a 75% conversion probability.

### Conversion prediction MVP

Initially, show fit score and priority. If a provisional conversion
range is included, label it as an uncalibrated heuristic and explain its
limitations. Prefer not to display a percentage until a defensible basis
exists.

### Later model phase

After sufficient historical sales outcomes are collected:

-   Define the conversion event.
-   Build a timestamped outcome dataset.
-   Train and evaluate a baseline model.
-   Validate probability calibration on held-out time periods.
-   Display model version, sample size, and evaluation window.
-   Monitor drift.

### Exit criteria

-   Every scored lead has a reproducible score breakdown.
-   Priority is configurable.
-   Missing data does not silently receive unjustified maximum scores.
-   UI distinguishes fit from conversion likelihood.

------------------------------------------------------------------------

## 7. Phase 4: NPPES V2 data ingestion

**Deferred.** Slice 1 uses the live CMS NPI Registry API instead (see
`docs/data-sources.md`). Build this phase only if the API's
1,200-records-per-query cap or missing provider counts becomes a real
problem. The handling rules below apply to the API connector as well.

### Tasks

1.  Review current CMS NPPES V2 documentation and file layout.
2.  Download the current full replacement file locally.
3.  Keep source archive outside the repository.
4.  Implement a streaming/chunked importer.
5.  Normalize taxonomy, names, addresses, phones, and provider types.
6.  Validate NPI format and preserve it as text.
7.  Build indexes or a local staging database/table for efficient
    filtering.
8.  Filter by selected state and specialty/taxonomy.
9.  Import qualifying organizations/providers into the normalized
    application model.
10. Track import version, source file date, and processing status.

### Important handling

-   Type 1 represents individual providers; Type 2 represents
    organizations.
-   Do not equate one Type 1 record with one independent practice.
-   Use Type 2 organization records as stronger organization candidates
    where appropriate.
-   Associate individual providers with organizations only when evidence
    supports it.
-   NPPES is not a ready-made email database.
-   NPI is not proof of active licensure or commercial suitability.

### Implementation approach

Do not transfer the entire large NPPES file to Supabase. Process it
locally in chunks. Keep only the normalized records needed by the
application in the hosted database, subject to source terms and
operational needs.

### Exit criteria

-   Import completes without exhausting memory.
-   Re-running the same source file is safe.
-   State and taxonomy filters return expected records.
-   Type 1 and Type 2 records remain distinguishable.
-   Import provenance is retained.

------------------------------------------------------------------------

## 8. Phase 5: Search jobs and local worker

### Search job lifecycle

Suggested states:

-   `queued`
-   `running`
-   `paused`
-   `completed`
-   `cancelled`
-   `failed`

### Tasks

-   Implement `POST /api/search`.
-   Validate specialty, state, target count, and options.
-   Persist job before execution.
-   Implement a local worker that claims eligible jobs.
-   Process records in bounded batches.
-   Persist counters and checkpoint after each batch.
-   Add retry rules for transient errors.
-   Make processing idempotent.
-   Implement cancellation and resume.
-   Expose job status and progress endpoint.
-   Add frontend progress UI.

### Progress metrics

-   Candidates discovered
-   Organizations accepted
-   Duplicates skipped
-   Websites found
-   Contacts discovered
-   Emails discovered
-   Validation states
-   Qualified leads
-   Source failures

### Reliability rules

-   Persist data incrementally.
-   Do not hold the only copy of job progress in process memory.
-   Use a job lock/claim mechanism to avoid two workers processing the
    same job.
-   Retry only transient failures and cap retries.
-   Record connector errors without stopping unrelated connectors.
-   Make restart/resume behavior testable.

### Exit criteria

-   A search runs independently of the browser request.
-   Progress updates in the UI.
-   Stopping and restarting the backend does not lose completed batches.
-   Resume does not create duplicate records.
-   Cancellation is respected between batches.

------------------------------------------------------------------------

## 9. Phase 6: Approved discovery connectors

Build a connector interface so new sources can be added without changing
the search engine.

### Connector contract

Each connector should define:

-   Stable connector name and version.
-   Access method (official API, downloadable dataset, permitted page
    retrieval).
-   Allowed fields.
-   Rate limits.
-   Retention restrictions.
-   Source policy review date.
-   Enabled/disabled state.
-   Search and normalization methods.
-   Error and retry behavior.

### Candidate sources

-   CMS/NPPES and other official government datasets.
-   Official practice websites.
-   Business directories only after reviewing their terms and permitted
    access methods.
-   Licensed APIs where terms allow the intended commercial use.

Do not implement bulk scraping for a directory merely because its pages
are publicly viewable. Some platforms restrict scraping, bulk export, or
retention of listing data.

### Exit criteria

-   Each connector can be independently enabled or disabled.
-   Source provenance is stored.
-   Rate limits and retries are respected.
-   A connector failure does not corrupt the search job.
-   No source is used without documented permission/policy review.

------------------------------------------------------------------------

## 10. Phase 7: Website, contact, and email enrichment

### Website enrichment

Where permitted, fetch official practice pages such as Contact, About,
Providers, Leadership, Locations, Services, and Billing.

Extract:

-   Organization name and aliases
-   Website and domain
-   Business phone
-   Public business email
-   Address/location
-   Provider names and roles
-   Practice manager or administrator details where published
-   Service indicators relevant to ZCS

### Email processing

Implement separate states:

1.  Not found
2.  Discovered
3.  Syntax valid
4.  Domain/MX valid
5.  Verified by provider
6.  Invalid
7.  Unknown

Do not represent MX validation as mailbox verification.

### Contact prioritization

Prioritize business decision-makers:

1.  Owner / practice owner
2.  Managing physician
3.  Practice manager
4.  Practice administrator
5.  Operations director
6.  RCM / billing manager

Retain source URL and evidence for each contact.

### Exit criteria

-   Enrichment only runs on eligible/approved sources.
-   Extracted facts retain provenance.
-   Email states accurately describe what was checked.
-   Failed enrichment does not delete the base organization.
-   Enrichment can be retried without duplicating contacts.

------------------------------------------------------------------------

## 11. Phase 8: Deduplication and lead quality

### Tasks

-   Normalize organization names.
-   Normalize phone numbers.
-   Normalize website domains.
-   Normalize addresses.
-   Match by NPI and source IDs where reliable.
-   Use weighted matching for records without strong identifiers.
-   Create a review state for ambiguous matches.
-   Preserve multiple locations and contacts.
-   Preserve all source records after merging.
-   Add quality flags for missing or conflicting data.

### Quality checks

-   Required organization name exists.
-   State is valid.
-   Website URL is normalized.
-   NPI format is checked when present.
-   Phone/email values are normalized.
-   No fabricated fields.
-   Every sourced fact has provenance.

### Exit criteria

-   Repeated imports do not multiply the same organizations.
-   Similar but distinct organizations are not automatically merged
    without adequate confidence.
-   Merge decisions preserve source and contact history.

------------------------------------------------------------------------

## 12. Phase 9: Excel export

### Tasks

-   Implement export filters.
-   Query the current database state at export time.
-   Generate workbook using OpenPyXL.
-   Include All Leads, Contacts, Activity History, and Summary sheets.
-   Include state and current outreach status.
-   Include lead score and priority.
-   Include conversion estimate only with an appropriate label and
    methodology.
-   Add filters, frozen headers, formatting, hyperlinks, and date
    formats.
-   Support all leads and selected leads.
-   Add a download endpoint and frontend export action.

### Exit criteria

-   Exported data matches current database records.
-   State and sales status are present.
-   Multiple contacts and activities are represented without losing
    data.
-   Workbook opens correctly in Excel.
-   Export filters work as expected.

------------------------------------------------------------------------

## 13. Phase 10: Testing and quality assurance

### Backend tests

-   Model constraints and migrations
-   API validation
-   Search job state transitions
-   Worker checkpoint/resume
-   Idempotent ingestion
-   NPPES normalization
-   Organization matching/deduplication
-   Scoring and priority boundaries
-   CRM activity history
-   Suppression checks
-   Excel content and formatting

### Frontend tests

-   Search form validation
-   Search progress display
-   Lead table filters/sorting/pagination
-   Lead details
-   Status updates
-   Activity creation
-   Pipeline transitions
-   Export flow
-   Error and empty states

### End-to-end scenarios

1.  Search for a specialty in one state.
2.  Import candidate organizations.
3.  Enrich a subset through permitted sources.
4.  Score and prioritize leads.
5.  Update a lead to email sent.
6.  Add a call activity and follow-up date.
7.  Stop and resume a search.
8.  Export selected leads.
9.  Verify Excel includes state, priority, and current CRM status.
10. Confirm no PHI has been collected.

------------------------------------------------------------------------

## 14. Phase 11: Security and operational readiness

-   Keep `.env` out of Git.
-   Keep Supabase service-role key on backend only.
-   Rotate credentials if accidentally exposed.
-   Restrict CORS to the local frontend origin.
-   Validate request payloads and query parameters.
-   Add safe logging and avoid logging secrets.
-   Keep downloaded NPPES data and exports out of source control.
-   Monitor Supabase database usage, egress, inactivity pausing, and
    backup limitations.
-   Create a backup/export procedure before relying on the free database
    for business-critical records.
-   Review connector terms periodically.
-   Maintain the suppression list independently of lead records.
-   Keep PHI out of the system.

------------------------------------------------------------------------

## 15. Suggested implementation milestones

  -----------------------------------------------------------------------
  Milestone               Deliverable             Completion test
  ----------------------- ----------------------- -----------------------
  M0                      Local project skeleton  Frontend and backend
                                                  run

  M1                      Database foundation     Migrations and DB
                                                  connectivity pass

  M2                      CRM core                Sample leads can be
                                                  managed end-to-end

  M3                      Scoring                 Explainable scores and
                                                  priorities appear

  M4                      NPPES importer          State/specialty
                                                  candidates are imported

  M5                      Search worker           Jobs run, checkpoint,
                                                  resume, and cancel

  M6                      Discovery/enrichment    Approved sources add
                                                  traceable data

  M7                      Deduplication           Repeated records are
                                                  handled safely

  M8                      Excel export            Formatted filtered
                                                  workbook downloads

  M9                      Hardening               Tests, security,
                                                  backup, and operational
                                                  checks pass
  -----------------------------------------------------------------------

Avoid committing to calendar durations until the first NPPES import and
source-permission review have been tested. Data-source coverage and
quality are likely to be the largest uncertainties.

------------------------------------------------------------------------

## 16. Suggested API contract

  ----------------------------------------------------------------------------------
  Method                  Route                          Request/response
                                                         responsibility
  ----------------------- ------------------------------ ---------------------------
  POST                    `/api/search`                  Create a search job

  GET                     `/api/search/{id}`             Retrieve job state and
                                                         counters

  POST                    `/api/search/{id}/cancel`      Request cancellation

  POST                    `/api/search/{id}/resume`      Resume eligible job

  GET                     `/api/leads`                   Paginated and filtered lead
                                                         list

  GET                     `/api/leads/{id}`              Organization, contacts,
                                                         locations, sources, score

  PATCH                   `/api/leads/{id}`              Update editable fields and
                                                         CRM status

  GET                     `/api/leads/{id}/activities`   Activity history

  POST                    `/api/leads/{id}/activities`   Add
                                                         call/email/note/follow-up

  GET                     `/api/dashboard/stats`         Dashboard aggregates

  GET                     `/api/exports/excel`           Download generated workbook

  GET                     `/api/sources`                 Connector configuration
                                                         list

  PATCH                   `/api/sources/{id}`            Enable/disable connector
  ----------------------------------------------------------------------------------

Document request and response schemas with Pydantic and OpenAPI. Use
consistent pagination and error response structures.

------------------------------------------------------------------------

## 17. Suggested environment variables

Example `.env.example`:

``` dotenv
APP_ENV=development
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_ORIGIN=http://localhost:3000

DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres

LOCAL_DATA_DIR=./data
NPPES_DATA_DIR=./data/nppes
EXPORT_DIR=./exports

WORKER_POLL_SECONDS=5
WORKER_BATCH_SIZE=250
MAX_SOURCE_RETRIES=3

LOG_LEVEL=INFO
```

Use the actual Supabase connection string and recommended SSL/connection
settings from the project dashboard. Do not commit real credentials. The
backend should read the database secret; frontend variables must never
contain the service-role key.

------------------------------------------------------------------------

## 18. Official reference sources

Verify the current documentation during implementation because file
formats, service limits, and terms can change.

-   CMS NPPES download files:
    https://download.cms.gov/nppes/NPI_Files.html
-   NPI Registry API documentation:
    https://npiregistry.cms.hhs.gov/api-page
-   CMS Provider Data: https://data.cms.gov/provider-data/
-   Supabase pricing: https://supabase.com/pricing
-   Supabase project pausing:
    https://supabase.com/docs/guides/platform/going-into-prod#project-pausing
-   CAN-SPAM compliance guidance:
    https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business

------------------------------------------------------------------------

## 19. Implementation rules for coding agents

When using Claude Code or another coding agent:

1.  Read the PRD and this implementation plan before changing files.
2.  Implement one milestone at a time.
3.  Do not silently remove or weaken requirements.
4.  Do not add paid APIs or scraping sources without explicit approval
    and a policy review.
5.  Do not invent data or claim a lead is verified without evidence.
6.  Keep scoring weights configurable and versioned.
7.  Keep fit score, priority, and conversion probability separate.
8.  Write migrations and tests with each backend feature.
9.  Keep secrets and source datasets out of Git.
10. Update documentation when routes, schemas, or environment variables
    change.
11. At the end of each milestone, report changed files, tests run, known
    limitations, and the next milestone.
12. Do not start a large scraping run until the CRM, deduplication,
    provenance, and persistence workflows are tested.

------------------------------------------------------------------------

## 20. Definition of done

The MVP is complete when a user can run the application locally, create
a state/specialty search, process permitted source data, persist and
resume results, inspect and prioritize leads, track outreach activities,
and export current records to Excel with state and sales status. All
collected data must be traceable, scoring must be explainable, and
conversion predictions must not overstate what the available evidence
supports.
