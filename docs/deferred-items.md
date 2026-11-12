# Deferred Items

Things the docs or code refer to that are intentionally not built yet. If a review suggests deleting a reference to one of these, add or keep the entry here instead of removing the reference.

| Item | Referenced in | Lands in | Trigger to build |
|---|---|---|---|
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
| Scoring thresholds tuned on real data | Real runs 2026-11-11: 116 of the Florida internal medicine leads came out critical | After more real searches | Priority does not separate leads usefully |
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
