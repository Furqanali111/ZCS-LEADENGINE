# Slice 2 Design: CRM

Date: 2026-11-11. Status: draft for owner review. Covers PRD FR-10, FR-12 and the rest of FR-11. Builds on slice 1 (lead discovery, merged to `develop`).

## 1. Goal

Turn the leads list into a working sales tool for ZCS: open a lead, log calls, emails, meetings and notes, set a follow-up date, move leads through a pipeline board, and see a dashboard. History is never erased. Opt-outs outlive leads.

## 2. Decisions made with the owner

- Suppression list matches on NPI, phone and email (one list, a `kind` per entry). Email entries are ready for slice 3.
- One next-follow-up date per lead. No multi-task follow-ups.
- Pipeline board: drag cards between all 10 status columns, plus a keyboard "Move to" menu.
- Single user, localhost, no login. No automatic outreach: activities are logged by hand.
- No conversion probability. The dashboard shows recorded outcomes only, with denominator and date range.

## 3. Approach

Snapshot columns on `organizations` plus an append-only `lead_activities` table. Every action that changes a lead writes one activity row and updates the snapshot in the same transaction. Rejected: deriving everything from activities (slow sorts and counts, more SQL for no benefit at this scale) and event sourcing (overkill).

## 4. Data model (migration 0004)

`organizations` gains:

| Column | Type | Meaning |
|---|---|---|
| `last_contacted_at` | timestamptz, null | Set when a call, email or meeting is logged |
| `next_follow_up_at` | date, null | Single follow-up date, set by the user |

Index on `next_follow_up_at`.

`lead_activities` (insert-only):

| Column | Type |
|---|---|
| `id` | uuid pk |
| `organization_id` | uuid fk to organizations, on delete restrict |
| `type` | text, check in (`call`, `email`, `meeting`, `note`, `status_change`, `outcome`) |
| `occurred_at` | timestamptz, default now |
| `summary` | text, max 2000 chars, required except `status_change` |
| `outcome` | text, null, check in (`no_answer`, `spoke`, `interested`, `not_interested`, `meeting_booked`, `converted`, `other`) |
| `from_status`, `to_status` | text, null, set only for `status_change` |
| `created_at` | timestamptz |

A trigger raises an error on UPDATE and DELETE, so history cannot be changed even by a bug. Index on (`organization_id`, `occurred_at` desc). Deleting an organization that has activities is refused (restrict); there is no delete-lead feature in this slice.

`suppression_list`:

| Column | Type |
|---|---|
| `id` | uuid pk |
| `kind` | text, check in (`npi`, `phone`, `email`) |
| `value` | text, normalized: NPI and phone as digits only, email lower-cased and trimmed |
| `reason` | text, null |
| `created_at` | timestamptz |

Unique on (`kind`, `value`). No foreign key to organizations, so it survives lead deletion. Row-level security enabled on both new tables, no policies, as in migration 0003.

## 5. Behavior

- **Status change** (PATCH or board drag): updates `crm_status` and `status_updated_at`, and inserts a `status_change` activity with from and to. Moving to or from `converted` or `not_interested` needs no extra step.
- **Logging an activity**: `call`, `email`, `meeting` set `last_contacted_at` to `occurred_at` (only if later than the current value). `note` and `outcome` do not. An optional `next_follow_up_at` in the same request updates the snapshot.
- **Suppression**: adding an entry that matches a lead (by NPI, by the lead's phone or fax digits, or by a stored email later) sets that lead to `do_not_contact` and logs a status change. Search saves check the list: a suppressed NPI keeps `do_not_contact` and never resets to `new`. Removing an entry does not change any lead's status. Suppressed leads stay in the table and board (`do_not_contact` column only) and are marked in the export with a Suppressed column, so nothing is silently dropped.
- **Overdue**: `next_follow_up_at < today` (local date). "Due" means today or earlier. Closed statuses (`converted`, `not_interested`, `do_not_contact`) never count as due.

## 6. API

All errors use the existing `{"error": {"code", "message"}}` shape. Lists are paginated.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/leads/{id}` | Full lead detail: row fields, contacts, locations, score components, source |
| PATCH | `/api/leads/{id}` | `crm_status` and/or `next_follow_up_at` (null clears it). Status change writes the activity |
| GET | `/api/leads/{id}/activities` | Newest first, paginated |
| POST | `/api/leads/{id}/activities` | Add an activity |
| GET | `/api/leads` | Existing, plus `follow_up` filter (`due`, `overdue`, `none`), `sort=follow_up`, search also matches contact names |
| GET | `/api/pipeline` | Per status: count and first N leads (default 20, `offset` for load more), ordered by score |
| GET | `/api/dashboard/stats` | See section 8 |
| GET, POST | `/api/suppression` | List, add |
| DELETE | `/api/suppression/{id}` | Remove an entry |
| POST | `/api/exports/excel` | Existing, with new columns: Last Contacted, Next Follow-up, Suppressed |

No endpoint updates or deletes an activity.

## 7. Screens

- **Lead detail** `/leads/[id]`: header with name, type, score, priority, status select, follow-up date picker, "Add to suppression list". Left: log form (type, date and time, summary, outcome) and the timeline, newest first, status changes shown as entries. Right: score explanation (six factors), contacts, locations, source and collection time. A mistake is corrected by adding a new note.
- **Pipeline** `/pipeline`: one column per status with count and the top 20 leads by score and "load more". Card: name, city and state, score, follow-up date (red when overdue). Drag to change status, plus a "Move to" menu per card for keyboard and touch. A failed move restores the card and shows the error. `do_not_contact` leads appear only in their own column.
- **Dashboard** `/` (replaces the redirect): tiles for total organizations, new leads, critical and high leads, follow-ups due, meetings scheduled, converted. Breakdowns by state and specialty (top 10), by status, latest search jobs. Conversion rate shown as "converted / contacted" with both numbers and the date range. Charts follow the `dataviz` skill.
- **Suppression** `/suppression`: table, add form (kind, value, reason), remove with confirmation.
- **Leads page**: follow-up filter and column, sort by follow-up, name links to the detail page.
- **Nav**: Dashboard, Search, Leads, Pipeline, Suppression.

## 8. Dashboard definitions

- Total organizations: count of organizations.
- New leads: `crm_status = new`.
- Critical and high: priority in (`critical`, `high`).
- Follow-ups due: non-closed leads with `next_follow_up_at <= today`.
- Meetings scheduled: `crm_status = meeting_scheduled`.
- Converted: `crm_status = converted`.
- Conversion rate: leads that reached `converted` within the date range divided by leads with a logged call, email or meeting within the same range. The API returns numerator, denominator, `from` and `to`. If the denominator is 0 the rate is null and the UI shows "No contacts yet". Default range: last 90 days, with a date range selector.
- Never shown as a probability or a prediction.

## 9. Out of scope

Multi-task follow-ups, sending email, editing source-provided fields, deleting leads, login, enrichment (slice 3), conversion probability (slice 4).

## 10. Testing

Backend, against the embedded Postgres: insert-only trigger rejects UPDATE and DELETE; status change writes exactly one activity and updates the snapshot atomically; activity types set `last_contacted_at` correctly; suppression matching, search-save protection and survival when an organization row without activities is removed; dashboard numbers on seeded data including the zero-denominator case; pipeline paging; new leads filters; export columns. Frontend: lint, type-check, build, and a manual walkthrough against the real database.

## 11. Acceptance criteria

1. Logging a call on a lead adds a timeline entry and updates Last contacted.
2. Changing status from the lead page and from a board drag each add a status-change entry, and earlier entries remain.
3. No API route or direct SQL update can edit or remove an activity.
4. Setting a follow-up date shows the lead under Follow-ups due on its date and in the leads filter.
5. Adding an NPI, phone or email to the suppression list marks matching leads `do_not_contact`, and a later search re-run does not reset them.
6. The suppression list has no link to lead rows: removing an organization row that has no activities leaves every suppression entry in place (tested at database level; the UI has no delete-lead action).
7. The board shows all 10 columns with counts, drag and the "Move to" menu both work, and a failed move reverts.
8. The dashboard shows the PRD FR-12 figures, and the conversion rate shows numerator, denominator and date range.
9. No conversion probability or percentage chance appears anywhere.
10. The lead detail shows the score explanation, contacts, locations and source provenance.
11. The Excel export includes Last Contacted, Next Follow-up and Suppressed.
12. No secret is committed and no Supabase key exists in frontend code.

## 12. Deferred to later slices

See `docs/deferred-items.md`. Slice 2 removes the CRM, suppression and `disqualified` rows from that list only when delivered. `disqualified` priority stays deferred.
