# Data Sources Register

The single list of every place ZCS LeadEngine may get data from, and whether it is allowed to.

**Rule:** no code fetches from a source unless its status here is `available`. This file is the human record; the `source_configs` table mirrors it at runtime.

## Statuses

| Status | Meaning | In the search form |
|---|---|---|
| `available` | Reviewed, permitted, and a connector is built | Selectable |
| `approved_not_built` | Reviewed and permitted, connector not written yet | Listed, greyed out |
| `not_reviewed` | Terms and access method not checked yet | Listed, greyed out |
| `rejected` | Reviewed, not permitted or not worth it | Hidden |

## Source selection in the frontend

The search form shows a "Sources" list read from `GET /api/sources`. The user ticks which `available` sources to use for that search. Sources in any other status are shown greyed out with their status, so the user can see what exists but cannot run it. The backend re-checks the status on every search: a request naming a source that is not `available` is refused.

## How a source becomes `available`

1. Read its terms of use, robots rules, and any official API or data license.
2. Record below: review date, access method, allowed fields, rate limit, retention limit.
3. Check that it adds data we lack (website, email, decision-maker) for healthcare practices.
4. Set `approved_not_built`, build the connector in its own PR, then set `available`.

If the terms forbid automated collection or commercial reuse, set `rejected` and write the reason.

## Core sources

| Source | Status | Access | Notes |
|---|---|---|---|
| CMS NPI Registry API | `approved_not_built` | Free public JSON API, no key | Slice 1 backbone. Details below. |
| CMS NPPES bulk file | `approved_not_built` | Free public download | Deferred. Fallback if the API cap or missing provider counts become a real problem. |
| Official practice websites | `not_reviewed` | Page fetch, per-site robots rules | Slice 3. Main route to websites, emails, and staff names. |

### CMS NPI Registry API (tested 2026-11-11)

Endpoint: `https://npiregistry.cms.hhs.gov/api/?version=2.1`

Tested query: `enumeration_type=NPI-2`, `taxonomy_description=Internal Medicine`, `state=TX`.

Verified in that test:

- `limit` accepts up to 200 per page, `skip` accepts 1000, so one query yields at most 1,200 records. Larger searches must be split, for example by city or postal code.
- On a 200-record page: phone present on 200, authorized official (name, title, phone) present on 200, any electronic endpoint (possible email) on 4.
- Each record carries `organizational_subpart` and, for subparts, `parent_organization_legal_business_name`.
- Taxonomy code and description, mailing and location addresses, "doing business as" names, and enumeration and last-updated dates are returned.

- `skip` above 1000 silently returns the last page again, so the cap is real.
- Result order is stable between identical calls. No total count is reported.
- `state` alone is refused; it needs another filter.
- `city` and `postal_code` (trailing `*` wildcard) work as extra filters.
- `taxonomy_description` matches any taxonomy on the record, not only the primary one.

Individual records (`enumeration_type=NPI-1`), same test date: 34 of 200 had `sole_proprietor = YES`, all 200 had a location phone. The flag is self-reported and is the only solo-practice signal the API offers. Slice 1 stores individual records only when the flag is YES.

Not verified yet: published rate limits.

How the fields feed scoring in slice 1:

| Score factor (PRD FR-08) | NPI field used |
|---|---|
| Specialty relevance | Taxonomy code and description |
| Practice size and independence | `organizational_subpart`, parent organization name |
| Business contactability | Phone, fax, location address |
| Decision-maker identified | Authorized official name and title |
| Fit with ZCS services | Taxonomy mapping (configurable) |
| Multiple providers or locations | Weak from the API alone. Scored low-confidence until the bulk file or enrichment adds counts. |

Known gaps: almost no emails, no websites, no reliable provider count per practice.

## Business directories (requested by the product owner)

All 30 are `not_reviewed`. The notes are first impressions from general knowledge, **not** a terms review, and must be confirmed before any status change.

General concerns that apply to most of them: they do not carry medical specialty or NPI, so every result must be matched back to an NPI record; many restrict automated collection in their terms; several are thin listing sites with sparse healthcare coverage.

| # | Directory | Status | First impression (unverified) |
|---|---|---|---|
| 1 | Allbiz | `not_reviewed` | General listing site |
| 2 | Yellow Pages | `not_reviewed` | Large U.S. coverage. Expect scraping restrictions. |
| 3 | Manta | `not_reviewed` | Small-business focus. Expect scraping restrictions. |
| 4 | Yelp | `not_reviewed` | Has an official API with limits on storing its data. Review the API terms, not the website. |
| 5 | Chamber of Commerce | `not_reviewed` | General listing site |
| 6 | Hotfrog | `not_reviewed` | Thin listing site |
| 7 | Brownbook | `not_reviewed` | Thin listing site |
| 8 | CylexUSA | `not_reviewed` | General listing site |
| 9 | MerchantCircle | `not_reviewed` | General listing site |
| 10 | Superpages | `not_reviewed` | Large U.S. coverage. Expect scraping restrictions. |
| 11 | EZlocal | `not_reviewed` | General listing site |
| 12 | CitySquares | `not_reviewed` | General listing site |
| 13 | Local.com | `not_reviewed` | General listing site |
| 14 | Desknow | `not_reviewed` | Unknown |
| 15 | Yellowbook | `not_reviewed` | General listing site |
| 16 | ShowMeLocal | `not_reviewed` | General listing site |
| 17 | eLocal | `not_reviewed` | General listing site |
| 18 | Opendi | `not_reviewed` | Thin listing site |
| 19 | Fyple | `not_reviewed` | Thin listing site |
| 20 | N49 | `not_reviewed` | Believed to be Canada-focused. Likely out of scope. |
| 21 | Tupalo | `not_reviewed` | Thin listing site |
| 22 | Infobel | `not_reviewed` | Sells business data commercially. A paid license may be the permitted route. |
| 23 | 2FindLocal | `not_reviewed` | General listing site |
| 24 | iBegin | `not_reviewed` | Thin listing site |
| 25 | Callupcontact | `not_reviewed` | Thin listing site |
| 26 | EnrollBusiness | `not_reviewed` | Thin listing site |
| 27 | Yalwa | `not_reviewed` | Thin listing site |
| 28 | YellowBot | `not_reviewed` | General listing site |
| 29 | MapQuest | `not_reviewed` | Has developer APIs. Review the API terms, not the website. |
| 30 | Better Business Bureau | `not_reviewed` | Trusted profiles. Expect scraping restrictions. |

Suggested review order when slice 3 starts: Yelp API, MapQuest API, Better Business Bureau, Yellow Pages, Superpages, Manta, then the rest only if those leave a gap.

## Review log

| Date | Source | Reviewer | Outcome |
|---|---|---|---|
| 2026-11-11 | CMS NPI Registry API | Claude (live test) | Works. Approved as slice 1 backbone. Rate limits still to confirm. |
