# Slice 3 Design: Automatic Enrichment

Date: 2026-11-12. Status: draft for owner review. Covers PRD FR-05, FR-06 and the website and decision-maker parts of FR-04. Builds on slices 1 and 2 (merged to `develop`).

## 1. Goal

One click on the search page runs the whole pipeline: NPI search, then for every saved lead find the official website, collect public business emails and named decision-makers, and verify each fact automatically. No manual step in between. Nothing is accepted unless an automatic check passes, so no data is invented.

## 2. Decisions made with the owner

- Fully automatic. No confirm queue. The lead page lets you reject a wrong website afterwards.
- Website discovery through the Brave Search API (key in backend `.env` as `BRAVE_API_KEY`).
- Extract emails and named staff with titles from the practice's own website pages.
- Yelp and similar listing sites: terms reviewed, see section 3.
- Deferred: the 30 business directories, cross-source dedup (PRD FR-07), better solo-practice flag, MX checks.

## 3. Source terms review (recorded in `docs/data-sources.md`)

| Source | Result | Why |
|---|---|---|
| Yelp (Fusion API and site) | `rejected` | API terms (checked 2026-11-12, terms.yelp.com/developers/api_terms): Yelp content may not be stored beyond 24 hours (5a), no scraping or bulk download (5a), no building a business database (5b), no commercial use without written consent (5d), no direct marketing use (5p). Only business IDs may be kept, for matching. Everything we would use it for is forbidden. The site itself blocks automated access, which we never bypass. |
| Brave Search API | `approved_not_built`, with a condition | The terms (updated Feb 2026, read through a search summary because the dashboard page could not be fetched) bar storing, caching or building a database of Search Results beyond transient use, unless the plan grants storage rights. Design consequence: Search Results (titles, snippets, ranks, result lists) are used in memory only and never stored. We store only a website URL that we ourselves fetched and verified on the practice's own page. The owner should confirm with Brave (searchapi-support@brave.com) or pick a plan with storage rights, because storing even the verified URL is a gray area. Becomes `available` only after that confirmation is recorded. |
| Practice websites (official, public) | `approved_not_built` then `available` | Public pages of the practice itself. Fetched with a descriptive user agent, robots.txt respected (including Crawl-delay), about one request per second per domain, no logins, no CAPTCHA or anti-bot bypass. |
| Google Business, Healthgrades, Facebook and other listing sites | `not_reviewed` | Not used. Their URLs are also on a blocklist, so a listing page can never become a lead's website. |

## 4. Approach

Enrichment is one more phase of the existing search job, run by the existing worker with the same checkpoint and resume pattern. A search job gets `enrich boolean`. After the NPI phases finish, the job walks its linked leads (`search_job_leads`) whose `enrichment_status` is `not_run` and enriches them one by one. Idempotent and resumable: a lead is marked as soon as it is done. Rejected: a separate job type and queue (more tables for no benefit), and enrichment inside the NPI loop (slows paging, couples failures).

## 5. Data model (migration 0005)

`organizations` gains: `website` (text, null), `website_evidence` (jsonb, null: page URL, which checks passed, checked time), `enrichment_status` (text, default `not_run`, check in `not_run`, `enriched`, `no_website_found`, `failed`, `rejected_by_user`), `enriched_at` (timestamptz, null).

`contacts` gains: `email` (text, null, lower-cased), `email_status` (text, null, only `found_on_page`), `source_url` (text, null), `collected_at` (timestamptz, null). The role check adds `staff` and `general`. A `general` contact is a shared mailbox such as info@; it has no name and stores the email address in `last_name` so the existing unique constraint on (organization, role, first name, last name) keeps one row per mailbox (shortcut, replace with a partial unique index if it gets awkward). Existing slice 1 code that deletes contacts by `source_key` keeps working: web contacts use `source_key = practice_website`.

`search_jobs` gains `enrich` (boolean, default false). Counters add `enrich_attempted`, `websites_found`, `no_website_found`, `emails_found`, `people_found`, `pages_fetched`, `blocked_by_robots`, `enrich_failures`. Checkpoint phase `enrich` stores nothing extra, because progress lives on each lead.

Seed: `source_configs` rows for `brave_search`, `practice_websites`, and `yelp` (rejected). RLS stays enabled on all tables (no new tables).

## 6. Pipeline per lead

1. Query: "{name} {city} {state}" through Brave, top 5 results, held in memory.
2. Candidate filter: drop blocklisted domains (listing, social, directory and government sites), keep at most 3 domains.
3. Fetch the candidate home page (HTML only, max 1 MB, 10 s timeout, robots respected).
4. **Website verification.** Accept the candidate only if the page text contains the lead's phone (10 digits, any formatting) from the organization or any stored location, or contains both the lead's cleaned name (all distinctive words) and its city. Otherwise try the next candidate. If none passes: `no_website_found`, nothing stored.
5. On accept: also fetch up to 4 more same-domain pages found by link text (contact, about, team, staff, providers), same rules.
6. **Email acceptance.** Collect addresses from `mailto:` links and plain text (no obfuscation decoding, no guessing, no pattern building). Accept an address if its domain equals the verified website's registrable domain, or it appears on a page that passed the phone check. Role addresses (info@, office@, billing@) are stored as `general`. Free mail domains (gmail, yahoo, outlook) are accepted only under the phone-check rule. Status is always `found_on_page`, never "verified" (CLAUDE.md: a page match is not mailbox verification).
7. **Person acceptance.** A name followed or preceded by a title from an allowlist (practice manager, office manager, administrator, owner, CEO, director, medical director, billing manager, MD, DO, NP, PA) on a team, about, staff or contact page of the verified site. Stored as `staff` with title and source URL.
8. **Suppression.** Before storing an email, check the suppression list (kind `email`). A suppressed address is not stored. If a stored contact email later matches a new suppression entry, the lead is set to `do_not_contact` (this closes the slice 2 deferred item, email matching). Lead-level matches on NPI and phone already apply.
9. Mark `enrichment_status` (`enriched` if a website was accepted) and `enriched_at`; rescore the lead.

Failures: network errors and 5xx retry twice with backoff, then count `enrich_failures` and mark `failed` (retried by the next run). HTTP 403, CAPTCHA pages and robots disallow are skipped, never retried, and counted. Brave 429 backs off; a persistent 401 or quota error pauses the job with a clear error. A missing `BRAVE_API_KEY` or a source not `available` refuses `enrich=true` at the API with a 422.

## 7. Scoring

The Decision-maker factor now also counts a `staff` contact with an allowed title, not only the NPI authorized official. `scoring_config.json` version bumps and `rescore.py` is run once. Fit score, priority and conversion probability stay three separate things.

## 8. API

| Method | Path | Change |
|---|---|---|
| POST | `/api/search` | New field `enrich` (bool). 422 `source_not_available` or `missing_api_key` when it cannot run |
| GET | `/api/search`, `/api/search/{id}` | Job output includes `enrich` and the new counters. `pages_fetched` counts NPI pages plus web pages for enrich jobs |
| GET | `/api/leads`, `/api/leads/{id}` | Add `website`, `enrichment_status`, `primary_email`, contacts with `email`, `email_status`, `source_url`, `collected_at`, and `website_evidence` on detail |
| PATCH | `/api/leads/{id}` | `reject_website: true` clears `website`, deletes the `practice_website` contacts, sets `rejected_by_user`, and logs a note activity |
| POST | `/api/exports/excel` | New columns Website, Email, Decision-maker (name and title) |
| GET | `/api/sources` | Lists the new source rows |

Errors keep the `{"error": {"code", "message"}}` shape.

## 9. Screens

- **Search page:** new toggle "Also find websites and emails". Disabled with a reason if the key or source is unavailable. Shows the expected Brave query count before starting.
- **Job list:** adds counts for websites found, emails found, people found, leads with no website.
- **Leads table:** Website and Email columns, a filter "has website" and "has email".
- **Lead page:** website link with the evidence line ("phone matched on /contact"), a "Not this website" button, contacts show email, status "Found on page" and a source link with collection time.

## 10. Rules kept

Zero PHI (business pages only), opt-in sources, never bypass robots, logins or CAPTCHAs, never invent data, honest email status, no automatic outreach, suppression outlives leads, secrets only in backend `.env`. Dangling references stay and go to `docs/deferred-items.md`.

## 11. Testing

Backend on the embedded Postgres, with a fake Brave client and local HTML fixtures (no live network): website accepted by phone, by name plus city, rejected on a chain or aggregator page; blocklist; email accepted by domain, by phone-check page, rejected for an unrelated address; role address stored as `general`; person with allowed title; suppressed email not stored; robots disallow; Crawl-delay; 403 skip; Brave 429 backoff; resume after a crash mid-lead; `enrich=true` refused without key; reject-website endpoint; export columns; scoring factor change. Frontend: lint, type-check, build, and a live run on a small real search against the real database once the key is set.

## 12. Acceptance criteria

1. One search with the toggle on produces leads with websites, emails and staff without any click in between.
2. Every stored website, email and person has a source URL, collection time and the check that passed.
3. A lead with no page that passes verification shows `no_website_found` and no website or email.
4. No Brave result text, rank or list is stored anywhere.
5. Robots disallow, 403 and CAPTCHA pages are skipped and counted.
6. A suppressed email is never stored, and a new email suppression entry marks matching leads `do_not_contact`.
7. A running job survives a restart and does not repeat finished leads.
8. "Not this website" removes the website and its web-derived contacts.
9. The Excel export has Website, Email and Decision-maker.
10. Email status text never says "verified".
11. Yelp is recorded as `rejected` and no code calls it.
12. No secret is committed. `BRAVE_API_KEY` appears only in backend `.env` and `.env.example`.

## 13. Out of scope

Directories, cross-source dedup and match review, MX or mailbox checks, email pattern guessing, obfuscated email decoding, JavaScript-rendered pages, paid enrichment APIs, outreach, the conversion probability (slice 4).

## 14. Open item for the owner

Confirm Brave's storage terms (section 3) before the live run. Until then the pipeline can be built and tested with the fake client, but `brave_search` stays `approved_not_built`.
