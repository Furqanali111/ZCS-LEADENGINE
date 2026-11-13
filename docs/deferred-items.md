# Deferred Items

Things the docs or code refer to that are intentionally not built yet. If a review suggests deleting a reference to one of these, add or keep the entry here instead of removing the reference.

| Item | Referenced in | Lands in | Trigger to build |
|---|---|---|---|
| Website phones saved as sourced phones (the `organization_phones` table already takes any `source_key`; the website enrichment only uses phones to verify a site today) | Maps design 2026-11-14 | Later | Salespeople want the website's phone beside the NPI and Maps ones |
| Google Maps lookup for non-hospital leads | Maps design 2026-11-14 | Later | Hospitals prove reliable and the owner asks for practices too |
| Google Maps lookup inside the desktop build (Playwright and Chromium are not bundled by PyInstaller yet) | Maps design 2026-11-14 | Later | The team needs the lookup button in the packaged app, not only from source |
| Hours not re-checked automatically; Maps hours go stale | Maps design 2026-11-14 | Later | A salesperson reports wrong hours |
| Business directory connectors (29 listed, Yelp rejected) | `docs/data-sources.md` | Later | Each one only after its terms review |
| Bulk NPPES file importer | PRD FR-03, Plan Phase 4 | After slice 1 | The 1,200-per-query API cap or missing provider counts hurts real searches |
| Cross-source deduplication and match review | PRD FR-07 | Later | When a directory source exists. Slices 1 to 3 dedupe by NPI only. |
| Conversion probability | PRD FR-09 | Slice 4 | Enough recorded sales outcomes to calibrate |
| Authentication and row-level security | PRD 4.2 | Later | A second user, or any non-localhost access |
| Paid enrichment or verification APIs | PRD 4.2 | Later | Measured coverage gap and explicit approval |
| Background queue (Redis, Celery) | PRD section 7 | Later | Measured worker bottleneck |
| A single ZIP code with more than 1,200 matching records cannot be split further, so the rest stay unreachable | Search continuation | Later | A real search reports fewer leads than expected for a dense ZIP |
| Search progress is a saved offset; the NPI Registry's order can shift as providers register, so a few records could be missed or repeated (repeats are filtered by NPI) | Search continuation | Later | A Start over run finds many leads the continued runs missed |
| Better solo-practice detection than the self-reported sole-proprietor flag | Slice 1 spec section 6 | Later | Too many solo leads turn out to be employed doctors |
| `disqualified` priority tier | PRD FR-08 | Slice 2 | Needs explicit rules or a user action |
| Automated frontend tests | Plan Phase 10 | Slice 2 | Slice 2 frontend is five pages checked by hand; add a test tool when a frontend bug repeats |
| Counter updates inside a page (today once per 200-record page, about 5 s per page) | Real run 2026-11-11 after batching | Later | Pages become slow enough that the UI looks stuck |
| Scoring thresholds tuned on real data | Real database 2026-11-12: with v2 thresholds 1,231 of 1,684 leads were critical. Config v3 sets critical 95, high 90, medium 80 (about 5, 21 and 47 percent of today's leads) | After enrichment fills websites, emails and staff | Priority still does not separate leads, or tiers feel too tight once enrichment raises scores |
| Fallback save path shares code with the batch path | Code review 2026-11-11 | Later | Either path changes and the two drift |
| Rescore with one query instead of one per organization (now also covers the staff lookup) | Code review 2026-11-11, Slice 3 | Later | `python -m app.rescore` takes minutes |
| Frontend focus and screen reader behavior verified only by code reading | Slice 2 review | Later | Before wider use or an accessibility complaint |
| MX or mailbox checks (email status stays `found_on_page`) | Slice 3 spec section 6 | Later | Bounce rate on outreach is a problem |
| JavaScript-rendered pages (plain HTML fetch only) | Slice 3 spec section 6 | Later | Many practice sites turn out empty to the fetcher |
| Obfuscated email decoding (`name [at] site`) | Slice 3 spec section 6 | Later | Many sites hide emails this way |
| Enrichment of leads from older searches (only leads linked to an enrich job are enriched) | Slice 3 | Later | Old leads need websites and emails without a re-search |
| Brave storage terms confirmation, then set `brave_search` and `practice_websites` to `available` | `docs/data-sources.md` | Before first enrich run | Owner confirms with Brave support or a plan with storage rights |
| Email attachment is first-page-wins (an address is attached to the first organization that surfaces it) | Slice 3 | Later | Shared addresses across organizations cause wrong attachments |
| Contacts do not store which check accepted them (the check is on `website_evidence`) | Final review, Slice 3 | Later | Someone needs per-contact provenance |
| Trigram indexes for lead search (the search ILIKEs raw columns across name, dba_name, city, npi and contacts, so a `lower()` trigram index is never used); `search._known_org_phones` uses a plain `regexp_replace` that the phone index does not match | Package E review | Later | The leads search page gets slow past tens of thousands of leads. Needs a query rewrite plus `pg_trgm`; check with `EXPLAIN` on Supabase |
| Salesperson names are not authenticated (anyone can send any `X-Salesperson`); no accounts or per-user permissions | Owner feature, 2026-11-13 | Before more than a few trusted users or any network exposure | Someone claims or releases under another name |
| Copy button fallback (`execCommand`) always says Copied and drops focus; copy code is duplicated in `call-today` and `contact-strip` (one `useCopy` hook) | UI review of PR 11 | Later | A copy fails silently or the two copies drift |
| Pipeline Move menu: focus after a move, ArrowDown to open, Home/End, menu rendered in a portal | UI review of PR 11 | Later | Keyboard or touch users report trouble |
| Backend `has_phone` lead filter so Call today does not search only the top 50 new leads | UI review of PR 11 | Later | Many top leads have no phone | 
| Request speed against the hosted database: each query costs about 150 ms round trip from the owner's PC. Measured 2026-11-13 on 1,762 leads: leads page 1.9 s before and 1.4 s after (window count, score joined), 200 per page 3.3 s, dashboard stats 1.9 s (about 10 queries), pipeline 0.8 s, `follow_up=due` 0.9 s. Next steps: fewer queries in dashboard stats, load locations and source records lazily when a row is opened, a closer database region or a connection pooler | Performance audit | Later | Salespeople say the pages feel slow |
| Code-signing certificate for the exe (SmartScreen shows "unknown publisher") | Desktop app section in README | Later | The app goes to people outside the team |
| In-app "new version available" banner | Desktop app section in README | Later | Windows stay open for days (updates apply on start) |
| Per-user accounts or a hosted deployment (the database URL sits on every PC) | Desktop app section in README | Later | More than a trusted team, or non-Windows users |
