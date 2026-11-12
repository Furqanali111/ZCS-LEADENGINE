# ZCS LeadEngine: Project Context

Pinned context for every session in this repo. Read first.

> **Before you touch any code**, read the doc that matches your task (see "Which doc to read" below). The PRD is the source of truth for what the product does. If a doc and this file disagree, stop and ask.

## The business

- **Company**: Zenith Care Solutions (ZCS)
- **Founders**: Furqan Ali (founder, software engineer) and Muhammad Usman (co-founder, PharmD, entrepreneur)
- **Operating from**: Pakistan, serving U.S. healthcare providers
- **Services ZCS sells**: Care Management (Chronic Care Management first), Revenue Cycle Management (billing, coding, credentialing, AR follow-up), Virtual Medical Staffing
- **Business model**: subcontracted staff provider. ZCS does not bill Medicare. The practice bills, and pays ZCS for the labor.
- **Ideal client**: independent and small-to-medium U.S. practices in primary care, internal medicine, and geriatrics. Hospitals and larger groups stay eligible but score lower.
- **Priority states**: FL, TX, AZ, CA
- **Decision-makers**: usually the practice manager, office manager, administrator, or owner, not always the MD

## What this product IS and ISN'T

- IS: an internal, single-user, local-first tool for ZCS to find, score, prioritize, and track U.S. healthcare practices as sales prospects, and export them to Excel.
- IS NOT: a public website, a patient system, an outreach sender, or a general web scraper.
- The public marketing website lives in its own repo. Never mix the two.

## Delivery slices (build in this order)

Each slice gets its own spec, plan, and build. Do not start a later slice early.

1. **Lead discovery**: search by specialty and state through the CMS NPI Registry API, save to Supabase, score and prioritize, basic leads table, Excel export. Sales status is a simple field in this slice.
2. **CRM**: lead detail, activity history, follow-ups, pipeline (Kanban), dashboard.
3. **Enrichment**: practice websites, public business emails, decision-makers, and any business directory that passes review.
4. **Conversion probability**: only after enough real sales outcomes exist.

## Which doc to read

| Task | Read first |
|---|---|
| Any feature work | [`ZCS_LeadEngine_Architectural_PRD.md`](ZCS_LeadEngine_Architectural_PRD.md) |
| Phase tasks and exit criteria | [`ZCS_LeadEngine_Implementation_Plan.md`](ZCS_LeadEngine_Implementation_Plan.md) |
| Slice 1 build | [`docs/superpowers/specs/2026-11-11-lead-discovery-design.md`](docs/superpowers/specs/2026-11-11-lead-discovery-design.md) |
| Slice 1 tasks, in order | [`docs/superpowers/plans/2026-11-11-lead-discovery.md`](docs/superpowers/plans/2026-11-11-lead-discovery.md) |
| Anything that fetches external data | [`docs/data-sources.md`](docs/data-sources.md) |
| Something referenced but not built yet | [`docs/deferred-items.md`](docs/deferred-items.md) |

## Tech stack (decided)

- **Frontend**: Next.js App Router, TypeScript, Tailwind CSS, shadcn/ui. Runs locally.
- **Backend**: Python, FastAPI, SQLAlchemy, Alembic, Pydantic. Runs locally.
- **Database**: Supabase-hosted PostgreSQL. The only hosted piece.
- **Excel**: OpenPyXL
- **Worker**: local Python, in-process to start. No Redis, no Celery, until measured load demands it.
- **Tests**: Pytest for backend, against an embedded Postgres (`pgserver`). Docker is not used: it cannot run on the owner's PC. One frontend test tool, chosen when the first frontend test is written.
- **Auth**: none in the MVP (single user, localhost only).

Rejected for the MVP: paid enrichment APIs, a cloud-hosted worker, automated email sending, an ML conversion model, uploading the bulk NPPES file to Supabase.

## Hard rules (data and compliance)

- **Zero PHI.** Never collect, store, or process patient records. Business contact data only.
- **Sources are opt-in.** No code may fetch from a source unless it is marked `available` in [`docs/data-sources.md`](docs/data-sources.md). Adding a source means reviewing its terms first and recording the review there.
- **Never bypass** logins, rate limits, robots rules, CAPTCHAs, or anti-bot protections.
- **Never invent data.** Return fewer leads instead of fabricating or padding. Every stored fact keeps its source and collection time.
- **Email status must be honest.** A DNS/MX check is not mailbox verification.
- **Fit score, priority, and conversion probability are three different things.** Never show a fit score as a percentage chance of conversion.
- **No automatic outreach.** The tool tracks emails and calls, it does not send them.
- **Suppression list outlives leads.** Deleting a lead never deletes its opt-out record.
- **Secrets**: the Supabase service-role key and database URL stay in the backend `.env`, never in frontend code, never in Git.
- **Keep out of Git**: `.env`, `data/`, `exports/`, logs, database dumps.

## Working style

- Ponytail mode, lazy senior dev: the smallest change that fully works. No premature abstraction.
- Reuse installed dependencies and existing components before adding anything new.
- Implement one slice and one milestone at a time. Report changed files, tests run, known limits, and the next step at the end of each.
- Subagent-driven implementation: run independent tasks in parallel whenever possible. Before dispatching, list which tasks share no files and no interfaces, put each parallel task in its own git worktree and branch, and cherry-pick the results onto the feature branch one at a time. Tasks that consume another task's output stay sequential. Never run two implementers in the same checkout.
- Write the migration and the test with each backend feature.
- Never use em dashes in any generated text, comments, commit messages, or documentation. Use a comma, colon, or rewrite the sentence.
- Update the docs when routes, schemas, or environment variables change.

## Git workflow: HARD RULES

- `develop` is the source of truth. **Never push to `develop` directly.** Every change goes through a PR.
- `release/vX.Y.Z` branches are cut from `develop`.
- Branch naming: `feature/<short-title>`, `defect/<short-title>`, `hotfix/<short-title>` (hotfixes are cut from the latest `release/*`).
- All lowercase, kebab-case, descriptive, 50 characters or fewer after the prefix.
- Rebase onto the latest `develop` before opening a PR. Never merge `develop` into a feature branch.
- Squash-merge only, linear history on `develop`.
- No force-push on shared branches. No direct push to `develop` or any `release/*`, including admin.
- No merge of your own PR without at least one approval.
- Hotfixes must be back-ported to `develop` through a second PR.
- **Commit messages: one-line subject only**, Conventional Commits (`feat(scope): ...`, `fix(scope): ...`, `docs(scope): ...`). No prose body. Explanations go in the PR body. Attribution lines (`Co-Authored-By:`) are still appended per harness rule.
- **Before handing a code PR back**: run `ponytail:ponytail-review` on the diff and apply its findings. Mandatory.
- **Dangling references are intentional.** If a review suggests removing a reference to something not built yet (a disabled source, a missing env var, a later-slice table), do not remove it. Add the missing target to [`docs/deferred-items.md`](docs/deferred-items.md) instead.

---

## Mandatory plugin usage

These plugins are installed in this workspace. Invoke the relevant skill before acting, every time.

### Ponytail (always active)

- `ponytail:ponytail` is active for every task.
- `ponytail:ponytail-review` before committing or finishing any non-trivial change.
- `ponytail:ponytail-audit` when asked to assess tech debt or scope creep.
- `ponytail:ponytail-gain` when evaluating whether a feature is worth adding.

### Superpowers (always check before acting)

- New feature, page, or slice: `superpowers:brainstorming` first.
- Bug or broken build: `superpowers:systematic-debugging` first.
- Multi-file change: `superpowers:writing-plans`, then `superpowers:executing-plans`.
- PR or branch finish: `superpowers:finishing-a-development-branch`.
- Code review: `superpowers:requesting-code-review` or `superpowers:receiving-code-review`.

### Database (Supabase)

- `supabase:supabase` for any Supabase project, connection, or key task.
- `supabase:supabase-postgres-best-practices` before writing or changing a migration, index, or heavy query.

### Data visualization

Any chart, stat tile, KPI row, or dashboard (the Dashboard page, score breakdowns, pipeline counts) must invoke the `dataviz` skill before any chart code or color choice.

### Frontend design

This is an internal app, not a marketing site, so the app-UI skills apply:

- `21st:21st-ui` before writing component markup, for shadcn/ui and Tailwind recipes.
- `impeccable:impeccable` for a finished screen (leads table, lead detail, pipeline, dashboard).
- `design:accessibility-review` before finishing any form-heavy or interactive screen.

### Engineering quality

- `engineering:code-review` before merging any PR or finishing a feature branch.
- `engineering:testing-strategy` when adding API routes, connectors, scoring, or dedup logic.
- `engineering:tech-debt` when asked about refactoring or dependency upgrades.

### Memory and context (claude-mem)

- `claude-mem:mem-search` before asking the user for context they may have already given.
- `claude-mem:learn-codebase` at the start of a session if codebase context is stale.
- `claude-mem:make-plan` before multi-session work.
- `claude-mem:handoff` when wrapping up a session.

---

## Quick reference

| Task | Invoke first |
|---|---|
| Any code change | `ponytail:ponytail` (always on) |
| New feature or slice | `superpowers:brainstorming` |
| Migration, index, query | `supabase:supabase-postgres-best-practices` |
| New data source or connector | read `docs/data-sources.md`, then `superpowers:brainstorming` |
| Chart, stat tile, dashboard | `dataviz` |
| UI component or screen | `21st:21st-ui`, then `impeccable:impeccable` |
| Accessibility check | `design:accessibility-review` |
| Bug fix | `superpowers:systematic-debugging` |
| Code review | `engineering:code-review` + `ponytail:ponytail-review` |
| Session start | `claude-mem:mem-search` |
| Session end | `claude-mem:handoff` |
| Tech debt or refactor | `ponytail:ponytail-audit` + `engineering:tech-debt` |
