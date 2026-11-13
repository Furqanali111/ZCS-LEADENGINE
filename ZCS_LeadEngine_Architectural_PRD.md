# ZCS LeadEngine

## Architectural Product Requirements Document (PRD)

**Document status:** Baseline product requirements\
**Product:** ZCS LeadEngine\
**Version:** 1.0\
**Prepared:** November 2026\
**Audience:** Product owner, engineering, implementation agents, and
future maintainers

------------------------------------------------------------------------

## 1. Product overview

ZCS LeadEngine is a local-first B2B healthcare prospecting and
lightweight CRM application for Zenith Care Solutions (ZCS). It
discovers relevant US healthcare practices, enriches their publicly
available business information, prioritizes prospects, tracks outreach
and sales progress, and exports usable lead data to Excel.

The product is intended to help ZCS identify and prioritize independent
and small-to-medium healthcare practices that may need:

-   Care Management
-   Revenue Cycle Management (RCM)
-   Virtual Medical Staffing

It is a business-to-business prospecting tool. It must not collect,
store, or process patient records or protected health information (PHI).

### Product principle

Build a reliable lead intelligence and sales workflow, not simply a web
scraper that produces a spreadsheet. Every lead should have traceable
sources, useful contact information where available, a transparent fit
score, a sales status, and a history of interactions.

------------------------------------------------------------------------

## 2. Goals and success criteria

### 2.1 Primary goals

1.  Discover healthcare organizations in the United States by specialty
    and state.
2.  Prioritize independent practices and small-to-medium groups while
    retaining relevant hospitals and larger healthcare groups.
3.  Enrich organizations with public business contact details and
    decision-maker information where permitted.
4.  Persist all collected data in a hosted PostgreSQL database.
5.  Calculate explainable lead-fit scores and priority tiers.
6.  Display an estimated conversion probability only when it is clearly
    distinguished from a fit score and appropriately calibrated.
7.  Provide CRM functionality for outreach stages, activities, notes,
    and follow-ups.
8.  Export all or selected records to formatted Excel workbooks.
9.  Run the frontend, backend, and data processing locally on the user's
    computer.

### 2.2 Success criteria

The MVP is successful when a user can:

-   Create a search using a specialty/keyword, one US state, and a
    target count.
-   Start a search and see its progress.
-   Resume or inspect a partially completed search after a local process
    interruption.
-   Browse saved leads and filter by state, specialty, priority, score,
    contactability, and CRM status.
-   Open a lead and inspect its organization details, contacts, sources,
    score explanation, and activity history.
-   Update a lead's sales status and record calls, emails, notes, and
    follow-up dates.
-   Export all or selected leads, including state and current sales
    status, to Excel.
-   See why a lead was assigned a particular priority.
-   Distinguish estimated fit from actual observed conversion
    performance.

The target of 500--1,000 leads per search is a requested target, not a
guarantee. The application must return fewer records rather than
fabricate records or lower quality standards to hit a number.

------------------------------------------------------------------------

## 3. Users and use cases

### Primary user

ZCS internal business development / sales operator.

### Core use cases

-   Find independent internal medicine practices in Texas.
-   Find family medicine practices in Florida.
-   Find geriatric care practices in a selected state.
-   Identify practice owners, managing physicians, practice managers,
    administrators, operations directors, or RCM managers where public
    information is available.
-   Prioritize practices that appear to have a strong fit for one or
    more ZCS services.
-   Track whether a practice has not been contacted, received an email,
    been called, expressed interest, booked a meeting, converted, or
    opted out.
-   Export a state-specific or campaign-specific lead list to Excel.

------------------------------------------------------------------------

## 4. Scope

### 4.1 MVP scope

-   Local Next.js frontend.
-   Local FastAPI backend.
-   Supabase-hosted PostgreSQL database.
-   User-configurable specialty/keyword, state, and target count.
-   CMS NPI Registry API as the foundational provider/organization
    source. The bulk NPPES file is a later fallback (see FR-03).
-   Source selection in the search form, limited to sources marked
    available in `docs/data-sources.md`.
-   Search jobs and progress tracking.
-   Organization, location, contact, and source records.
-   Permitted website discovery and public business email extraction.
-   Deduplication and source provenance.
-   Explainable rule-based lead scoring.
-   Priority tiers.
-   CRM status management, activities, notes, and follow-ups.
-   Excel exports.
-   Basic dashboard and pipeline/Kanban view.
-   Local worker with persistent checkpoints.

### 4.2 Later enhancements

-   Additional directory or data-provider integrations after terms and
    licensing review.
-   Paid email discovery and verification APIs if ROI justifies them.
-   Calibrated conversion prediction using ZCS's own sales outcomes.
-   Multiple users, authentication, and role-based access if the product
    becomes shared.
-   Automated outreach only after a separate compliance and product
    decision.
-   Cloud-hosted worker or queue infrastructure if local processing
    becomes a bottleneck.
-   Advanced analytics, campaign attribution, and sales forecasting.

### 4.3 Explicit non-goals for MVP

-   Patient acquisition or patient-level records.
-   PHI collection or storage.
-   Automatic bulk email sending.
-   Bypassing website protections, authentication, rate limits, or
    access controls.
-   Guaranteed mailbox existence based solely on DNS/MX checks.
-   Guaranteed 500--1,000 qualified leads for every search.
-   A complex distributed scraping platform.
-   A trained machine-learning conversion model before enough labeled
    outcomes exist.

------------------------------------------------------------------------

## 5. Functional requirements

### FR-01: Search creation

The user must be able to specify:

-   Specialty or keyword, such as Internal Medicine, Family Medicine, or
    Geriatric Care.
-   One US state per search.
-   Target number of leads, with 500--1,000 supported as common targets.
-   Organization inclusion preferences: independent practices, groups,
    and hospitals.
-   Optional enrichment toggles, such as website, business email, phone,
    and decision-maker discovery.
-   Which data sources to use. The form lists every source from the
    source register. Only sources with status `available` can be
    selected; the rest are shown greyed out with their status. The
    backend must refuse a search that names a source that is not
    `available`.

Each search must create a persistent `search_job` record, including the
sources selected.

### FR-02: Search execution and progress

The system must:

-   Execute long-running searches outside the HTTP request/response
    cycle.
-   Persist job status, counters, errors, and checkpoints.
-   Display progress in the UI.
-   Support queued, running, paused, completed, cancelled, and failed
    states.
-   Avoid losing already collected data when a worker stops.
-   Permit safe retry/resume without creating duplicate organizations.

Progress counters should include, where applicable:

-   Candidates discovered
-   Organizations accepted
-   Duplicates skipped
-   Websites found
-   Contacts discovered
-   Emails discovered
-   Emails with syntax/domain checks completed
-   Qualified leads
-   Failed source operations

### FR-03: Foundational data ingestion

Use CMS NPPES/NPI data as a foundational source for provider and
organization discovery.

Decision (November 2026): the first build uses the live CMS NPI Registry
API, not the bulk file. It needs no download or import pipeline and was
tested successfully (see `docs/data-sources.md`). One API query returns
at most 1,200 records, so larger searches must be split, for example by
city. The bulk NPPES file is deferred and is built only if that cap or
the lack of provider counts becomes a real problem.

Requirements:

-   Query the NPI Registry API by state, taxonomy/specialty, and
    organization type, page by page, saving each page before fetching
    the next.
-   Use the `organizational_subpart` flag and parent organization name
    as independence evidence.
-   Store the authorized official as the first decision-maker contact,
    with NPPES as its source.
-   Solo doctors are valid leads. Store an individual (Type 1) record
    as a lead only when it is marked as a sole proprietor, and label
    it as a solo provider. The flag is self-reported, so say so in the
    score explanation.
-   If the bulk file is added later: support the current NPPES V2
    format, import it locally once, and do not upload the entire file
    to Supabase.
-   Support filtering by state, taxonomy/specialty, provider type, and
    organization type where the source provides those fields.
-   Treat NPI as a string.
-   Distinguish Type 1 individual providers from Type 2 organizations.
-   Do not treat every individual provider as a separate practice.
-   Group providers into an organization only when there is evidence
    supporting the relationship.
-   NPI presence does not by itself prove current license status,
    quality, or commercial fit.

### FR-04: Organization and practice discovery

The system should discover organizations through approved data sources
and official practice websites.

-   Independent and small-to-medium practices receive higher priority.
-   Hospitals and healthcare groups remain eligible.
-   Candidate directories must be reviewed individually before automated
    collection.
-   Source-specific access method, approved fields, rate limits, and
    retention restrictions must be configurable.
-   Do not assume that a public webpage can be bulk-scraped or that
    directory content can be retained indefinitely.

### FR-05: Website enrichment

Where permitted, inspect official practice pages such as:

-   Contact
-   About
-   Providers / Our Team
-   Leadership
-   Locations
-   Services
-   Billing / Insurance

Capture public business information only. Store the source URL and
collection timestamp for each extracted fact.

### FR-06: Contact and email enrichment

Capture business contacts where publicly available, prioritizing:

-   Owner / practice owner
-   Managing physician
-   Practice manager
-   Practice administrator
-   Operations director
-   RCM / billing manager

Email discovery must distinguish discovery from verification. Suggested
states:

-   `not_found`
-   `discovered`
-   `syntax_valid`
-   `domain_valid`
-   `verified_by_provider`
-   `invalid`
-   `unknown`

DNS/MX validation confirms domain mail configuration, not that a
particular mailbox exists. SMTP probing must not be represented as
definitive verification and should generally be avoided.

Do not infer personal contact details without reliable evidence. Prefer
published business contact channels.

### FR-07: Deduplication

The system must prevent duplicate organizations across searches.

Use a combination of identifiers and normalized attributes, such as:

-   NPI
-   Normalized organization name
-   Website domain
-   Phone number
-   Address
-   External source IDs

Deduplication must preserve multiple locations, multiple contacts, and
source records. Potential matches should be reviewable rather than
blindly merged when confidence is low.

### FR-08: Lead scoring and priority

Each lead must receive an explainable fit score from 0--100. Initial
proposed weights:

  Factor                              Maximum
  --------------------------------- ---------
  Specialty relevance                      25
  Practice size and independence           20
  Fit with ZCS services                    20
  Business contactability                  15
  Decision-maker identified                10
  Multiple providers or locations          10
  **Total**                           **100**

The scoring implementation must store component scores, weights/model
version, total score, calculation time, and human-readable reasons.

Suggested priority tiers:

-   Critical: Contact first
-   High: Strong prospect
-   Medium: Worth pursuing
-   Low: Lower potential
-   Disqualified: Not a suitable prospect

Thresholds must be configurable and versioned. Disqualification should
require explicit rules or user action, not merely a low score.

Contactability and business fit should remain distinguishable. A highly
suitable practice with no discovered email may still be a good business
prospect.

### FR-09: Conversion probability

The product may display an estimated conversion probability, but must
not equate a lead-fit score with conversion probability.

MVP behavior:

-   Display the fit score and priority.
-   If a conversion estimate is shown before sufficient outcome data
    exists, label it clearly as a provisional heuristic or range, not a
    statistically validated probability.
-   Show the evidence and limitations behind the estimate.
-   Do not present illustrative percentages as observed conversion
    rates.

Later behavior:

-   Collect outcome labels such as replied, interested, meeting
    scheduled, proposal sent, converted, not interested, and
    do-not-contact.
-   Build a calibrated model only after enough representative historical
    outcomes exist.
-   Evaluate calibration, precision/recall where relevant, sample size,
    and drift.
-   Display the model version, data window, and confidence/limitations.
-   Avoid training leakage from events that occur after the prediction
    timestamp.

### FR-10: CRM and sales pipeline

Each organization must have a current sales status. Suggested statuses:

-   `new` / Not contacted
-   `researching`
-   `email_sent`
-   `called`
-   `called_no_answer` (called, nobody picked up; the No answer quick button sets it)
-   `follow_up_required`
-   `interested`
-   `meeting_scheduled`
-   `not_interested`
-   `converted`
-   `do_not_contact`

The system must also retain immutable activity history. Changing the
current status must not delete prior calls, emails, or notes.

Track:

-   Current status
-   Last contacted date
-   Next follow-up date
-   Activity type
-   Activity timestamp
-   Notes
-   Optional outcome

The suppression list must be independent of lead deletion so an
opted-out address is not accidentally reintroduced.

### FR-11: Lead management UI

Users must be able to:

-   Browse leads in a table.
-   Search by organization, contact, city, website, or NPI.
-   Filter by state, specialty, organization type, score, priority, CRM
    status, email status, and search job.
-   Sort by score, priority, updated date, and follow-up date.
-   Edit permitted fields.
-   View source provenance.
-   Add notes and activities.
-   Set follow-up dates.
-   View a lead's score explanation.

### FR-12: Dashboard and pipeline

Dashboard should include:

-   Total organizations
-   New leads
-   Critical/high-priority leads
-   Leads by state and specialty
-   Leads by CRM status
-   Search job activity
-   Follow-ups due
-   Meetings scheduled
-   Conversions
-   Actual conversion rates based on recorded outcomes, with denominator
    and date range

Pipeline should provide a Kanban view by CRM status.

### FR-13: Excel export

Excel must be generated from the current database state, not from a
separately maintained workbook.

Support exporting all or selected leads and filtering by state,
specialty, status, priority, and email availability.

Suggested workbook sheets:

1.  **All Leads**
2.  **Contacts**
3.  **Activity History**
4.  **Summary**

Suggested All Leads columns:

-   Lead ID
-   Organization Name
-   Specialty
-   Organization Type
-   Website
-   Business Phone
-   Business Email
-   Email Verification Status
-   Contact Person
-   Contact Designation
-   Contact Email
-   City
-   State
-   ZIP
-   NPI
-   Provider Count
-   Number of Locations
-   Care Management Fit
-   RCM Fit
-   Staffing Fit
-   Lead Score
-   Lead Priority
-   Estimated Conversion Probability (only when appropriately labeled)
-   Source
-   Source URL
-   Last Verified
-   Outreach Status
-   Next Follow-up
-   Last Contacted

Workbook usability:

-   Header filters
-   Frozen header row
-   Sensible column widths
-   Hyperlinks for websites and source URLs
-   Conditional formatting for priority and sales status
-   Date formatting
-   No misleading conversion percentages

### FR-14: Source provenance

For each collected record or material fact, preserve:

-   Source name
-   Source URL or source identifier
-   External record ID if available
-   Collection method
-   Collection timestamp
-   Applicable policy/configuration status
-   Last reviewed date for source permission

### FR-15: Configuration

Provide environment-based configuration for:

-   Database URL
-   Backend secrets
-   Local source-data directory
-   Worker batch size and rate limits
-   Enabled data connectors
-   Scoring weights and thresholds
-   Export directory

Never expose the Supabase service-role key to the browser.

------------------------------------------------------------------------

## 6. Non-functional requirements

### Reliability

-   Search progress and collected data must persist incrementally.
-   A worker restart must not lose completed batches.
-   Retries must be bounded and idempotent.
-   One source failure must not necessarily fail the entire search.
-   Errors must be logged with source/job context without logging
    secrets.

### Performance

-   Use pagination for lead lists.
-   Add indexes for common filters and joins.
-   Process large NPPES files locally in batches.
-   Avoid loading entire large datasets into application memory where
    streaming/chunking is possible.
-   Use asynchronous/background processing for long jobs.

### Security

-   Keep service-role credentials on the backend only.
-   Use environment variables and a `.env` file excluded from version
    control.
-   Validate and constrain all user inputs.
-   Apply least-privilege database access.
-   If multiple users are added, implement authentication and row-level
    security before exposing shared access.
-   Do not store PHI.

### Maintainability

-   Separate source connectors from business logic.
-   Use migrations for schema changes.
-   Keep scoring weights and thresholds configurable.
-   Add tests for normalization, deduplication, scoring, CRM
    transitions, and exports.
-   Record connector versions and policy reviews.

### Cost

-   Prefer free official data and open-source tools initially.
-   Keep large source downloads local.
-   Use Supabase Free initially, while monitoring database size, egress,
    inactivity pausing, and backup limitations.
-   Add paid enrichment only after measuring coverage and business
    value.

------------------------------------------------------------------------

## 7. High-level architecture

``` text
User
 |
 v
Next.js + TypeScript frontend (local)
 |
 | HTTP / JSON
 v
FastAPI backend (local)
 |
 +--> Search orchestration
 |      |
 |      +--> Local Python worker
 |              |
 |              +--> NPPES importer / local normalized data
 |              +--> Approved source connectors
 |              +--> Official website enrichment
 |              +--> Email/domain checks
 |              +--> Deduplication
 |              +--> Lead scoring
 |
 +--> CRM and lead services
 +--> Excel export service
 |
 v
Supabase PostgreSQL (hosted)
```

The local application performs collection and processing. Supabase
provides persistent hosted storage. The user's computer must be running
for local search jobs to execute; data already saved in Supabase remains
available when the computer is off.

### Recommended technology

  Layer                 Choice
  --------------------- ---------------------------------
  Frontend              Next.js, TypeScript
  Styling/UI            Tailwind CSS, shadcn/ui
  Backend               Python, FastAPI
  Database              Supabase PostgreSQL
  ORM                   SQLAlchemy
  Migrations            Alembic
  Validation            Pydantic
  Data processing       Pandas
  Excel                 OpenPyXL
  HTML parsing          BeautifulSoup, Scrapy
  Browser automation    Playwright, only where allowed
  Email/domain checks   Python email parsing, dnspython
  Worker                Local Python worker initially
  Tests                 Pytest, frontend test tooling

Do not introduce Redis/Celery in the MVP unless measured workload
requires it.

------------------------------------------------------------------------

## 8. Data model

Recommended normalized tables:

### `search_jobs`

Stores query parameters, target count, state, status, progress counters,
errors, timestamps, and resumable checkpoint metadata.

### `organizations`

Stores the practice or healthcare organization: name, organization type,
specialty, website, business phone, NPI where applicable, provider
count, current CRM status, score summary, and timestamps.

### `locations`

Stores one or more physical/business locations per organization,
including address, city, state, ZIP, and primary-location flag.

### `contacts`

Stores business contacts and roles, with email/phone/LinkedIn only when
supported by a permitted public source.

### `source_records`

Stores provenance and external IDs for organizations, locations, and
contacts.

### `search_job_leads`

Links organizations to search jobs, preserving the fact that one lead
may appear in multiple searches.

### `lead_scores`

Stores score components, weights/model version, total fit score,
priority, explanation, optional conversion estimate metadata, and
calculation time.

### `lead_activities`

Stores calls, emails, notes, follow-ups, meetings, and outcomes as an
append-only history.

### `email_verifications`

Stores email validation events and their method/provider/time.

### `suppression_list`

Stores opted-out or otherwise suppressed addresses independently of
organization records.

### `source_configs`

Stores each connector's access method, approved fields, rate limits,
retention rules, policy review date, and enabled state.

### Important modeling rules

-   Organization state and sales status are different concepts.
-   State should use validated two-letter US state codes.
-   NPI should be stored as a string.
-   One organization may have multiple locations and contacts.
-   Preserve raw/source evidence separately from normalized fields.
-   `current_status` is the current CRM snapshot; `lead_activities` is
    the history.
-   Never delete suppression records just because a lead is deleted.
-   Use UUID primary keys and database constraints/indexes.

------------------------------------------------------------------------

## 9. API outline

Suggested endpoints:

  ------------------------------------------------------------------------------
  Method                  Endpoint                       Purpose
  ----------------------- ------------------------------ -----------------------
  POST                    `/api/search`                  Create and queue a
                                                         search

  GET                     `/api/search/{id}`             Get job status and
                                                         progress

  POST                    `/api/search/{id}/cancel`      Cancel a running search

  POST                    `/api/search/{id}/resume`      Resume a paused/failed
                                                         eligible search

  GET                     `/api/leads`                   Paginated, filtered
                                                         lead list

  GET                     `/api/leads/{id}`              Lead details

  PATCH                   `/api/leads/{id}`              Update editable lead
                                                         fields/status

  GET                     `/api/leads/{id}/activities`   List activity history

  POST                    `/api/leads/{id}/activities`   Add activity

  GET                     `/api/dashboard/stats`         Dashboard metrics

  GET                     `/api/exports/excel`           Generate Excel export

  GET                     `/api/sources`                 List configured data
                                                         sources

  PATCH                   `/api/sources/{id}`            Enable/disable a
                                                         connector
  ------------------------------------------------------------------------------

Use Pydantic request/response schemas, pagination, consistent error
formats, and validation. The final API contract should be documented
before frontend/backend integration.

------------------------------------------------------------------------

## 10. Lead scoring and conversion methodology

### Fit score

The initial 100-point weighted model is a business-fit heuristic. Store
the individual component values and explanations so the score is
auditable.

### Priority

Priority is a configurable mapping from fit score plus explicit
exclusion/qualification rules. It is a workflow aid, not a guarantee of
commercial success.

### Conversion probability

Do not call a heuristic fit score a conversion probability. Before
sufficient outcomes exist, either omit probability or label a
provisional estimate prominently.

Once outcome data is sufficient:

1.  Define a clear conversion event, such as becoming a paying ZCS
    customer.
2.  Define the prediction timestamp and feature cutoff.
3.  Build a dataset of leads with known outcomes.
4.  Split training and evaluation data by time to reduce leakage.
5.  Compare simple baselines before using complex models.
6.  Evaluate calibration and performance on held-out data.
7.  Monitor drift and retrain only when justified.
8.  Show sample size, model version, and evaluation date in the UI.

------------------------------------------------------------------------

## 11. Compliance and responsible data collection

-   This product is for B2B business prospecting, not patient data.
-   Never collect PHI or patient-level records.
-   Review terms, licenses, API rules, robots directives, rate limits,
    and retention requirements for each source.
-   Do not bypass access controls, anti-bot measures, or technical
    restrictions.
-   Do not assume directory listings may be scraped, stored, or reused
    commercially.
-   Prefer official government datasets and official practice websites
    where permitted.
-   Store source provenance and collection time.
-   Respect CAN-SPAM for US commercial email, including B2B email:
    accurate sender information, non-deceptive subjects, required postal
    address, opt-out mechanism, and timely suppression.
-   Do not automatically send outreach in the MVP.
-   Maintain a durable suppression list.
-   Have legal/compliance review before scaling collection or outreach.

------------------------------------------------------------------------

## 12. Risks and mitigations

  -----------------------------------------------------------------------
  Risk                                Mitigation
  ----------------------------------- -----------------------------------
  NPPES contains individual providers Separate Type 1 and Type 2; group
  rather than distinct practices      only with supporting evidence

  NPPES lacks a ready-made email list Enrich from permitted official
                                      practice websites

  Duplicate organizations across      Normalize, match, retain
  searches                            provenance, and review uncertain
                                      matches

  Directory terms restrict bulk       Source-by-source approval and
  collection                          connector configuration

  Email validation is overstated      Store validation method/status; MX
                                      is not mailbox proof

  Target count cannot be reached      Treat count as a target; return
                                      qualified results only

  False conversion predictions        Separate fit score from calibrated
                                      probability

  Local computer shuts down           Persist batches and checkpoints in
  mid-search                          database

  Supabase Free limitations           Monitor capacity, inactivity,
                                      egress, and backup strategy

  Unwanted outreach after opt-out     Independent suppression list and
                                      checks before any future outreach
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 13. Acceptance criteria

The MVP is ready for practical use when:

1.  A user can create a state/specialty search.
2.  A search job is persisted before processing begins.
3.  The worker can process records in batches and persist progress.
4.  A worker restart does not duplicate completed organizations.
5.  Lead records preserve state, source, and collection time.
6.  A lead can have multiple locations and contacts.
7.  Lead score and priority are explainable.
8.  Conversion estimates are not misrepresented as actual conversion
    rates.
9.  CRM status changes are reflected in the pipeline and exports.
10. Activities remain available as history.
11. Suppressed contacts cannot be accidentally reintroduced into
    outreach lists.
12. Excel exports contain state and current outreach status.
13. Common filters and pagination work.
14. No PHI is collected or stored.
15. Connector policy restrictions are respected.

------------------------------------------------------------------------

## 14. Product decisions to keep configurable

Do not hard-code these permanently:

-   Priority thresholds
-   Scoring weights
-   Specialty taxonomy mapping
-   Organization-type preferences
-   Search target limits
-   Source enablement and rate limits
-   Email verification rules
-   CRM status labels
-   Export columns
-   Conversion model thresholds and version

These should be configurable so ZCS can refine its sales strategy
without redesigning the application.

------------------------------------------------------------------------

## 15. Delivery slices

The MVP is built in slices. Each slice gets its own design spec,
implementation plan, and build, and must be usable on its own.

  Slice   Name                     Delivers
  ------- ------------------------ ------------------------------------------
  1       Lead discovery           Search by specialty and state through the
                                   NPI Registry API, persistent search jobs,
                                   source selection, NPI-based dedup, fit
                                   score and priority, basic leads table
                                   with filters, Excel export. Sales status
                                   is a simple editable field.
  2       CRM                      Lead detail, activity history, follow-ups,
                                   suppression list, pipeline (Kanban),
                                   dashboard.
  3       Enrichment               Practice websites, public business emails,
                                   decision-makers, reviewed business
                                   directories, cross-source dedup.
  4       Conversion probability   Calibrated estimate from recorded sales
                                   outcomes.

Requirement coverage by slice:

-   Slice 1: FR-01, FR-02, FR-03, FR-08, FR-13, FR-14, FR-15, and the
    table and filter parts of FR-11. FR-07 by NPI only.
-   Slice 2: FR-10, FR-12, and the rest of FR-11.
-   Slice 3: FR-04, FR-05, FR-06, and the rest of FR-07.
-   Slice 4: the later behavior in FR-09.

Items not yet built are tracked in `docs/deferred-items.md`.
