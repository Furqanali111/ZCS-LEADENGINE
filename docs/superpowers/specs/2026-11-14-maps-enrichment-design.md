# Maps enrichment design (hospital phone and hours)

Approved by the owner in chat on 2026-11-14.

## Why
Salespeople need a phone that reaches the hospital and to know when it is open. The NPI phone is self-reported and sometimes wrong. The owner chose Google Maps as the second source, after being told it breaks Google's terms (`docs/data-sources.md`, "Google Maps (2026-11-14)").

## Goals
- Save the NPI phone and the Google Maps phone side by side, each with source and date, and show both on the lead card, each with a Copy button.
- Show opening hours and a link to the same Maps search on the card, so a salesperson can check by hand.
- Any later phone source (website, other) lands in the same table.

## Non-goals
Practices and other non-hospital leads, automatic re-checks, replacing the NPI phone, bundling Chromium in the desktop build.

## Approaches
1. Address-only View Map link, then click the building's directory entry. The owner's first idea. Live probe: it lands on a street pin, and picking from the directory chose a wrong place twice.
2. Search name plus address, read the place page. Chosen. Reached the right hospital most times.
3. Google Places API. The owner ruled it out.

## Design
- Table `organization_phones` (phone, source_key, source_url, collected_at, differs_from_npi). The NPI phone stays on `organizations.phone` and is listed first by the API, so nothing needs a backfill.
- Columns on `organizations`: `hours` (JSONB with source and date), `maps_status`, `maps_checked_at`, `maps_url`. Source row `google_maps` in `source_configs`.
- Connector `app/sources/gmaps.py` (Playwright, one place page, stops on CAPTCHA). Logic in `app/services/maps.py`. Match rule: street number and name, city and state agree with an NPI address of the lead.
- `POST /api/leads/{id}/maps` for one hospital, `python -m app.enrich_maps` for a batch.
- Card: phones list with source labels and a "differs" note, "Open in Google Maps", today's hours with the full week, and a lookup button.
