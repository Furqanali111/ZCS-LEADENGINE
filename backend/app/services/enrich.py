"""Per-lead website enrichment. Brave results live in memory only; only verified facts are stored."""
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Contact, Location, Organization, SearchJob, SearchJobLead, SourceRecord
from app.services.leads import save_score
from app.services.scoring import load_config, score
from app.services.suppression import suppressed_emails
from app.services.verify import (candidate_roots, extract_emails, extract_people, page_links, page_text,
                                 registrable_domain, relevant_links, verify_website)
from app.sources.brave import SearchError
from app.sources.npi_registry import normalize
from app.sources.web import FetchFailed, Page

logger = logging.getLogger(__name__)

SOURCE_KEY = "practice_website"
SKIP = ("enriched", "rejected_by_user")
COUNTERS = ("enrich_attempted", "websites_found", "no_website_found", "emails_found", "people_found",
            "pages_fetched", "blocked_by_robots", "enrich_failures")
NEAR = 200  # an email this close to a person's name in the page text belongs to that person
AUTH_MESSAGE = "Brave Search rejected the API key. Check BRAVE_API_KEY and resume the job."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _near(text: str, first: str, last: str, email: str) -> bool:
    low = text.lower()
    at = low.find(email)
    if at < 0:
        return False

    def close(word: str) -> bool:
        return any(abs(m.start() - at) <= NEAR for m in re.finditer(re.escape(word.lower()), low))

    return close(first) and close(last)


def enrich_lead(session: Session, org: Organization, *, search: Callable[[str], list[str]],
                fetch: Callable[[str], Page | None], counters: dict, now: Callable[[], datetime] = _now) -> str:
    if org.enrichment_status in SKIP:
        return org.enrichment_status
    for k in COUNTERS:
        counters.setdefault(k, 0)
    counters["enrich_attempted"] += 1
    stamp = now()

    query = " ".join(p for p in (org.name, org.city, org.state) if p)
    phones = [p for p in [org.phone, *session.scalars(select(Location.phone).where(Location.organization_id == org.id))] if p]

    accepted: tuple[Page, str] | None = None
    for root in candidate_roots(search(query)):
        page = fetch(root)
        if page is None:
            continue
        check = verify_website(page_text(page.html), phones=phones, name=org.name, city=org.city)
        if check:
            accepted = (page, check)
            break

    session.execute(delete(Contact).where(Contact.organization_id == org.id, Contact.source_key == SOURCE_KEY))
    if accepted is None:
        org.website, org.website_evidence = None, None
        org.enrichment_status = "no_website_found"
        counters["no_website_found"] += 1
    else:
        home, check = accepted
        parts = urlsplit(home.url)
        site = registrable_domain(parts.hostname or "")
        pages = [home]
        for url in relevant_links(page_links(home.html, home.url), site):
            if url != home.url and (extra := fetch(url)) is not None:
                pages.append(extra)
        org.website = f"{parts.scheme}://{parts.netloc}/"
        org.website_evidence = {"page_url": home.url, "check": check, "checked_at": stamp.isoformat()}
        org.enrichment_status = "enriched"
        counters["websites_found"] += 1
        _store_contacts(session, org, pages, site, phones, stamp, counters)
    org.enriched_at = stamp
    _rescore(session, org)
    return org.enrichment_status


def _store_contacts(session: Session, org: Organization, pages: list[Page], site: str, phones: list[str],
                    stamp: datetime, counters: dict) -> None:
    rows: dict[tuple[str, str, str], dict] = {}  # keyed like the unique constraint, first page wins
    for page in pages:
        text = page_text(page.html)
        verified = verify_website(text, phones=phones, name=org.name, city=org.city) == "phone"
        hits = extract_emails(page.html, text, site_domain=site, phone_verified=verified)
        blocked = suppressed_emails(session, {h.email for h in hits})
        hits = [h for h in hits if h.email not in blocked]
        base = {"organization_id": org.id, "source_key": SOURCE_KEY, "source_url": page.url, "collected_at": stamp}
        used: set[str] = set()
        for p in extract_people(text):
            row = {**base, "role": "staff", "first_name": p.first_name, "last_name": p.last_name, "title": p.title}
            for h in hits:
                if not h.general and h.email not in used and _near(text, p.first_name, p.last_name, h.email):
                    row.update(email=h.email, email_status="found_on_page")
                    used.add(h.email)
                    break
            rows.setdefault(("staff", p.first_name, p.last_name), row)
        for h in hits:
            if h.email not in used:
                rows.setdefault(("general", "", h.email),
                                {**base, "role": "general", "first_name": "", "last_name": h.email,
                                 "email": h.email, "email_status": "found_on_page"})
    session.add_all(Contact(**r) for r in rows.values())
    session.flush()
    counters["emails_found"] += sum(1 for r in rows.values() if r.get("email"))
    counters["people_found"] += sum(1 for r in rows.values() if r["role"] == "staff")


def _rescore(session: Session, org: Organization) -> None:
    rec = session.scalars(select(SourceRecord).where(SourceRecord.organization_id == org.id)
                          .order_by(SourceRecord.collected_at.desc()).limit(1)).first()
    if rec is None:
        return
    session.flush()
    staff = session.scalars(select(Contact.id).where(
        Contact.organization_id == org.id, Contact.role == "staff",
        Contact.title.is_not(None), Contact.title != "").limit(1)).first() is not None
    save_score(session, org, score(normalize(rec.raw), load_config(), staff_with_title=staff))


def enrich_job_leads(session_factory, job_id: UUID, *, search: Callable[[str], list[str]],
                     fetch: Callable[[str], Page | None], fetch_stats: dict, sleep: Callable[[float], None]) -> str:
    with session_factory() as session:
        ids = list(session.scalars(
            select(SearchJobLead.organization_id).join(Organization, Organization.id == SearchJobLead.organization_id)
            .where(SearchJobLead.search_job_id == job_id, Organization.enrichment_status.in_(("not_run", "failed")))
            .order_by(SearchJobLead.created_at, SearchJobLead.id)))
        seen = {k: fetch_stats.get(k, 0) for k in ("pages_fetched", "blocked_by_robots")}
        for org_id in ids:
            if session.get(SearchJob, job_id, populate_existing=True).cancel_requested:
                return "cancelled"
            org = session.get(Organization, org_id, populate_existing=True)
            attempt: dict = {}
            failure = None
            for retry in (False, True):
                attempt = {}
                try:
                    enrich_lead(session, org, search=search, fetch=fetch, counters=attempt)
                    failure = None
                    break
                except SearchError as e:
                    session.rollback()
                    if e.kind == "auth":
                        session.get(SearchJob, job_id, populate_existing=True).error = AUTH_MESSAGE
                        session.commit()
                        return "paused"
                    failure = e.kind
                    if e.kind == "rate_limited" and not retry:
                        sleep(5)
                        continue
                    break
                except FetchFailed:
                    session.rollback()
                    failure = "fetch"
                    break
            if failure:
                logger.warning("enrich job %s: lead failed (%s)", job_id, failure)
                session.get(Organization, org_id, populate_existing=True).enrichment_status = "failed"
                attempt = {"enrich_attempted": 1, "enrich_failures": 1}
            job = session.get(SearchJob, job_id, populate_existing=True)
            counters = {k: 0 for k in COUNTERS} | dict(job.counters or {})
            for k, v in attempt.items():
                counters[k] += v
            for k, was in seen.items():
                counters[k] += fetch_stats.get(k, 0) - was
                seen[k] = fetch_stats.get(k, 0)
            job.counters = counters
            session.commit()
    return "done"
