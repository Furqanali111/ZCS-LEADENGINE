"""Runs one search job: page through the NPI Registry, upsert, score, link, checkpoint. Resumable and idempotent."""
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import delete, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import US_STATES
from app.models import Contact, LeadScore, Location, Organization, SearchJob, SearchJobLead, SourceRecord
from app.services.leads import save_score
from app.services.scoring import load_config, score
from app.sources.npi_registry import MAX_SKIP, PAGE_SIZE, NormalizedLead, SourceError, fetch_page, normalize

logger = logging.getLogger(__name__)

SOURCE_KEY = "npi_registry"
BATCH = 100  # leads per multi-row statement, keeps bind parameters far below the driver limit
COUNTERS = ("candidates_seen", "accepted_new", "accepted_existing", "skipped_excluded", "skipped_inactive",
            "skipped_not_sole_proprietor", "skipped_works_at_known_org", "pages_fetched", "source_failures")
PHASES = (("practices", "NPI-2", "include_practices"), ("solo", "NPI-1", "include_solo"))
ORG_FIELDS = ("name", "dba_name", "organization_type", "parent_organization_name", "primary_taxonomy_code",
              "primary_taxonomy_desc", "phone", "fax", "state", "city")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fetch(fetch, client, sleep, retries: int, **query) -> list[dict]:
    for attempt in range(retries + 1):
        try:
            return fetch(client, **query)
        except (SourceError, httpx.HTTPError):
            if attempt == retries:
                raise
            sleep(2 ** attempt)


def _known_org_phones(session: Session, leads: list[NormalizedLead]) -> set[str]:
    """Digits-only phones of stored non-solo organizations that match any of the leads' phones, in one query."""
    phones = {l.phone for l in leads if l.phone}
    if not phones:
        return set()
    # shortcut: regexp over every non-solo phone per page, fine for thousands of orgs; add a digits column if it gets slow
    stored = func.regexp_replace(Organization.phone, r"\D", "", "g")
    return set(session.scalars(select(stored).where(Organization.organization_type != "solo_provider", stored.in_(phones))))


def _skip_reason(job: SearchJob, phase: str, lead: NormalizedLead, known_phones: set[str]) -> str | None:
    if not lead.active:
        return "skipped_inactive"
    if phase == "practices":
        if (lead.organization_type == "subpart" and not job.include_subparts) or \
                (lead.organization_type == "hospital" and not job.include_hospitals):
            return "skipped_excluded"
    else:
        if not lead.sole_proprietor:
            return "skipped_not_sole_proprietor"
        if lead.phone and lead.phone in known_phones:
            return "skipped_works_at_known_org"
    if lead.state not in US_STATES:  # organizations.state is NOT NULL and limited to the 50 states plus DC
        return "skipped_excluded"
    return None


def _save_lead(session: Session, job: SearchJob, lead: NormalizedLead, config: dict) -> str | None:
    """Upserts one accepted lead and links it to the job. Returns the counter to bump, or None if already linked."""
    values = {f: getattr(lead, f) for f in ORG_FIELDS}
    stmt = insert(Organization).values(npi=lead.npi, **values)
    # crm_status and status_updated_at are never in set_, so a re-run keeps the operator's work
    stmt = stmt.on_conflict_do_update(index_elements=[Organization.npi], set_={**values, "updated_at": func.now()})
    org_id, was_new = session.execute(stmt.returning(Organization.id, literal_column("xmax = 0"))).one()

    # Core statements run immediately, so the delete lands before the inserts that may reuse the same keys
    session.execute(delete(Location).where(Location.organization_id == org_id))
    if lead.locations:
        rows = [{**loc, "organization_id": org_id, "address_1": loc["address_1"] or "", "zip": loc["zip"] or ""}
                for loc in lead.locations]
        session.execute(insert(Location).values(rows).on_conflict_do_nothing())

    if lead.contact:
        c = lead.contact
        stmt = insert(Contact).values(organization_id=org_id, role=c["role"], first_name=c["first_name"] or "",
                                      last_name=c["last_name"] or "", title=c["title"], phone=c["phone"],
                                      source_key=SOURCE_KEY)
        session.execute(stmt.on_conflict_do_update(
            constraint="uq_contacts_org_role_name",
            set_={"title": stmt.excluded.title, "phone": stmt.excluded.phone, "updated_at": func.now()}))

    stmt = insert(SourceRecord).values(organization_id=org_id, source_key=SOURCE_KEY, external_id=lead.npi,
                                       raw=lead.raw, collected_at=func.now())
    session.execute(stmt.on_conflict_do_update(
        constraint="uq_source_records_source_external",
        set_={"organization_id": org_id, "raw": stmt.excluded.raw, "collected_at": func.now(), "updated_at": func.now()}))

    save_score(session, session.get(Organization, org_id), score(lead, config))

    linked = session.scalar(insert(SearchJobLead).values(search_job_id=job.id, organization_id=org_id, was_new=was_new)
                            .on_conflict_do_nothing().returning(SearchJobLead.id))
    if linked is None:
        return None
    return "accepted_new" if was_new else "accepted_existing"


def _save_batch(session: Session, job: SearchJob, leads: list[NormalizedLead], config: dict) -> list[str | None]:
    """Upserts distinct-NPI leads in a handful of multi-row statements. Same result as _save_lead per lead."""
    scores = [score(l, config) for l in leads]
    cols = (*ORG_FIELDS, "fit_score", "priority")
    stmt = insert(Organization).values([
        {"npi": l.npi, **{f: getattr(l, f) for f in ORG_FIELDS}, "fit_score": s.total, "priority": s.priority}
        for l, s in zip(leads, scores)])
    # crm_status and status_updated_at are never in set_, so a re-run keeps the operator's work
    stmt = stmt.on_conflict_do_update(index_elements=[Organization.npi],
                                      set_={**{c: stmt.excluded[c] for c in cols}, "updated_at": func.now()})
    rows = session.execute(stmt.returning(Organization.npi, Organization.id, literal_column("xmax = 0"))).all()
    org_id = {npi: i for npi, i, _ in rows}
    was_new = {npi: new for npi, _, new in rows}

    session.execute(delete(Location).where(Location.organization_id.in_(org_id.values())))
    loc_rows, seen = [], set()
    for l in leads:
        for loc in l.locations:
            row = {**loc, "organization_id": org_id[l.npi], "address_1": loc["address_1"] or "", "zip": loc["zip"] or ""}
            key = (row["organization_id"], row["purpose"], row["address_1"], row["zip"])
            if key not in seen:
                seen.add(key)
                loc_rows.append(row)
    if loc_rows:
        session.execute(insert(Location).values(loc_rows).on_conflict_do_nothing())

    contact_rows = [{"organization_id": org_id[l.npi], "role": l.contact["role"], "first_name": l.contact["first_name"] or "",
                     "last_name": l.contact["last_name"] or "", "title": l.contact["title"], "phone": l.contact["phone"],
                     "source_key": SOURCE_KEY} for l in leads if l.contact]
    if contact_rows:
        stmt = insert(Contact).values(contact_rows)
        session.execute(stmt.on_conflict_do_update(
            constraint="uq_contacts_org_role_name",
            set_={"title": stmt.excluded.title, "phone": stmt.excluded.phone, "updated_at": func.now()}))

    stmt = insert(SourceRecord).values([{"organization_id": org_id[l.npi], "source_key": SOURCE_KEY, "external_id": l.npi,
                                         "raw": l.raw, "collected_at": func.now()} for l in leads])
    session.execute(stmt.on_conflict_do_update(
        constraint="uq_source_records_source_external",
        set_={"organization_id": stmt.excluded.organization_id, "raw": stmt.excluded.raw, "collected_at": func.now(),
              "updated_at": func.now()}))

    stmt = insert(LeadScore).values([{"organization_id": org_id[l.npi], "components": s.components, "total": s.total,
                                      "priority": s.priority, "config_version": s.config_version,
                                      "calculated_at": func.now()} for l, s in zip(leads, scores)])
    session.execute(stmt.on_conflict_do_update(
        index_elements=[LeadScore.organization_id],
        set_={**{c: stmt.excluded[c] for c in ("components", "total", "priority", "config_version")},
              "calculated_at": func.now(), "updated_at": func.now()}))

    linked = set(session.scalars(insert(SearchJobLead).values(
        [{"search_job_id": job.id, "organization_id": org_id[l.npi], "was_new": was_new[l.npi]} for l in leads])
        .on_conflict_do_nothing().returning(SearchJobLead.organization_id)))
    return [None if org_id[l.npi] not in linked else "accepted_new" if was_new[l.npi] else "accepted_existing"
            for l in leads]


def _save_each(session: Session, job: SearchJob, leads: list[NormalizedLead], config: dict, counters: dict) -> list[str | None]:
    """Fallback: one savepoint per lead, so a bad record costs one source failure and nothing else."""
    outcomes = []
    for lead in leads:
        try:
            with session.begin_nested():
                outcomes.append(_save_lead(session, job, lead, config))
        except Exception as e:
            logger.warning("search job %s: record NPI %s failed: %s", job.id, lead.npi, type(e).__name__)
            counters["source_failures"] += 1
    return outcomes


def _process_page(session: Session, job: SearchJob, phase: str, records: list[dict], counters: dict, config: dict) -> bool:
    """Filters the page in Python, then writes the accepted leads in batches. Returns True once the target is reached."""
    parsed = []  # (NPI, lead or None when the record is malformed)
    for raw in records:
        npi = raw.get("number")
        try:
            if not npi:
                raise ValueError("record has no NPI number")
            parsed.append((npi, normalize(raw)))
        except Exception as e:
            logger.warning("search job %s: record NPI %s failed: %s", job.id, npi, type(e).__name__)
            parsed.append((npi, None))
    known = _known_org_phones(session, [l for _, l in parsed if l]) if phase == "solo" else set()

    accepted: dict[str, NormalizedLead] = {}  # a repeated NPI in one page keeps its last copy and counts once
    for _, lead in parsed:
        if counters["accepted_new"] + counters["accepted_existing"] + len(accepted) >= job.target_count:
            break
        counters["candidates_seen"] += 1
        if lead is None:
            counters["source_failures"] += 1
        elif reason := _skip_reason(job, phase, lead, known):
            counters[reason] += 1
        else:
            accepted[lead.npi] = lead

    leads = list(accepted.values())
    for i in range(0, len(leads), BATCH):
        chunk = leads[i:i + BATCH]
        try:
            with session.begin_nested():
                outcomes = _save_batch(session, job, chunk, config)
        except Exception as e:
            logger.warning("search job %s: batched save failed (%s), retrying record by record", job.id, type(e).__name__)
            outcomes = _save_each(session, job, chunk, config, counters)
        for outcome in outcomes:
            if outcome:
                counters[outcome] += 1
    return counters["accepted_new"] + counters["accepted_existing"] >= job.target_count


def _finish(session: Session, job: SearchJob, status: str, error: str | None = None) -> None:
    job.status, job.error, job.finished_at = status, error, _now()
    session.commit()


def run_job(session_factory, job_id: UUID, *, fetch=fetch_page, sleep=time.sleep) -> None:
    settings = get_settings()
    config = load_config()
    with session_factory() as session, httpx.Client(timeout=30) as client:
        job = session.get(SearchJob, job_id)
        if job.cancel_requested:
            return _finish(session, job, "cancelled")
        job.status, job.error, job.finished_at = "running", None, None
        job.started_at = job.started_at or _now()
        session.commit()

        counters = {k: 0 for k in COUNTERS} | (job.counters or {})
        phases = [(name, enum) for name, enum, toggle in PHASES if getattr(job, toggle)]
        names = [name for name, _ in phases]
        checkpoint = job.checkpoint or {}
        resumed = checkpoint.get("phase") in names
        i = names.index(checkpoint["phase"]) if resumed else 0
        skip = checkpoint.get("skip", 0) if resumed else 0

        while i < len(phases):
            phase, enumeration_type = phases[i]
            try:
                records = _fetch(fetch, client, sleep, settings.max_source_retries, enumeration_type=enumeration_type,
                                 specialty=job.specialty, state=job.state, city=job.city, skip=skip)
            except (SourceError, httpx.HTTPError) as e:
                job.counters, job.checkpoint = dict(counters), {"phase": phase, "skip": skip}
                return _finish(session, job, "failed", str(e) or type(e).__name__)

            counters["pages_fetched"] += 1
            reached = _process_page(session, job, phase, records, counters, config)
            skip += PAGE_SIZE
            job.checkpoint = {"phase": phase, "skip": skip}
            if not reached and (len(records) < PAGE_SIZE or skip > MAX_SKIP):
                i, skip = i + 1, 0
                if i < len(phases):
                    job.checkpoint = {"phase": phases[i][0], "skip": 0}
            job.counters = dict(counters)
            cancelled = session.scalar(select(SearchJob.cancel_requested).where(SearchJob.id == job.id))

            # one commit per page: rows, counters, checkpoint and any final status together
            if reached or (not cancelled and i == len(phases)):
                return _finish(session, job, "completed")
            if cancelled:
                return _finish(session, job, "cancelled")
            session.commit()
            sleep(settings.npi_page_delay_seconds)

        _finish(session, job, "completed")
