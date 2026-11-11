# Deferred Items

Things the docs or code refer to that are intentionally not built yet. If a review suggests deleting a reference to one of these, add or keep the entry here instead of removing the reference.

| Item | Referenced in | Lands in | Trigger to build |
|---|---|---|---|
| Practice website enrichment | PRD FR-05 | Slice 3 | Slice 2 accepted |
| Email discovery and validation states | PRD FR-06 | Slice 3 | With website enrichment |
| Business directory connectors (30 listed) | `docs/data-sources.md` | Slice 3 | Each one only after its terms review |
| Bulk NPPES file importer | PRD FR-03, Plan Phase 4 | After slice 1 | The 1,200-per-query API cap or missing provider counts hurts real searches |
| Cross-source deduplication and match review | PRD FR-07 | Slice 3 | When a second source exists. Slice 1 dedupes by NPI only. |
| Conversion probability | PRD FR-09 | Slice 4 | Enough recorded sales outcomes to calibrate |
| Authentication and row-level security | PRD 4.2 | Later | A second user, or any non-localhost access |
| Paid enrichment or verification APIs | PRD 4.2 | Later | Measured coverage gap and explicit approval |
| Background queue (Redis, Celery) | PRD section 7 | Later | Measured worker bottleneck |
| Automatic splitting of searches past the 1,200 cap | Slice 1 spec section 3 | After slice 1 | The optional city filter proves too manual |
| Better solo-practice detection than the self-reported sole-proprietor flag | Slice 1 spec section 6 | Slice 3 | Too many solo leads turn out to be employed doctors |
| `disqualified` priority tier | PRD FR-08 | Slice 2 | Needs explicit rules or a user action |
| Automated frontend tests | Plan Phase 10 | Slice 2 | Slice 2 frontend is five pages checked by hand; add a test tool when a frontend bug repeats |
| Counter updates inside a page (today once per 200-record page, about 5 s per page) | Real run 2026-11-11 after batching | Later | Pages become slow enough that the UI looks stuck |
| Scoring thresholds tuned on real data | Real runs 2026-11-11: 116 of the Florida internal medicine leads came out critical | After more real searches | Priority does not separate leads usefully |
| Search index on lead name, city and NPI (trigram) | Code review 2026-11-11 | Later | The leads table gets slow past tens of thousands of rows |
| Fallback save path shares code with the batch path | Code review 2026-11-11 | Later | Either path changes and the two drift |
| Rescore with one query instead of one per organization | Code review 2026-11-11 | Later | `python -m app.rescore` takes minutes |
| Email suppression matching (entries stored, no lead emails yet) | Slice 2 spec | Slice 3 | Emails are collected for leads |
| Index for phone digit matching in suppression and search saves (regexp scan) | Slice 2 review | Later | Add or save gets slow past tens of thousands of leads |
| Frontend focus and screen reader behavior verified only by code reading | Slice 2 review | Later | Before wider use or an accessibility complaint |
