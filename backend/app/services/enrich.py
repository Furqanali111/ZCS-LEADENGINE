"""Per-lead website enrichment. Brave results live in memory only; only verified facts are stored."""
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Contact, Location, Organization, SearchJob, SearchJobLead
from app.services.leads import rescore_org
from app.services.suppression import suppressed_emails
from app.services.verify import (blocked_host, candidate_roots, extract_emails, extract_people, page_links,
                                 page_text, registrable_domain, relevant_links, verify_website)
from app.sources.brave import SearchError
from app.sources.web import FetchFailed, Page

logger = logging.getLogger(__name__)

SOURCE_KEY = "practice_website"
SKIP = ("enriched", "rejected_by_user")
COUNTERS = ("enrich_attempted", "websites_found", "no_website_found", "emails_found", "people_found",
            "pages_fetched", "blocked_by_robots", "skipped", "enrich_failures")
AUTH_MESSAGE = "Brave Search rejected the API key. Check BRAVE_API_KEY and resume the job."


def _now() -> datetime:
    return datetime.now(timezone.utc)


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

    roots = candidate_roots(search(query))
    accepted: tuple[Page, str, str] | None = None  # page, its text, which check passed
    reachable = 0
    for root in roots:
        try:
            page = fetch(root)
        except FetchFailed:  # a dead candidate must not fail the lead, the next one may be the real site
            continue
        reachable += 1
        if page is None or blocked_host(urlsplit(page.url).hostname or ""):  # a redirect may land on a directory site
            continue
        text = page_text(page.html)
        if check := verify_website(text, phones=phones, name=org.name, city=org.city):
            accepted = (page, text, check)
            break
    if roots and not reachable:  # every candidate was unreachable: retry next run, keep what is stored
        org.enrichment_status = "failed"
        return "failed"

    session.execute(delete(Contact).where(Contact.organization_id == org.id, Contact.source_key == SOURCE_KEY))
    if accepted is None:
        org.website, org.website_evidence = None, None
        org.enrichment_status = "no_website_found"
        counters["no_website_found"] += 1
    else:
        home, text, check = accepted
        parts = urlsplit(home.url)
        site = registrable_domain(parts.hostname or "")
        pages = [(home, text, check == "phone")]
        for url in relevant_links(page_links(home.html, home.url), site):
            if url == home.url:
                continue
            try:
                extra = fetch(url)
            except FetchFailed:  # keep what the home page produced
                continue
            if extra is not None:
                t = page_text(extra.html)
                pages.append((extra, t, verify_website(t, phones=phones, name=org.name, city=org.city) == "phone"))
        org.website = f"{parts.scheme}://{parts.netloc}/"
        org.website_evidence = {"page_url": home.url, "check": check, "checked_at": stamp.isoformat()}
        org.enrichment_status = "enriched"
        counters["websites_found"] += 1
        _store_contacts(session, org, pages, site, stamp, counters)
    org.enriched_at = stamp
    rescore_org(session, org)
    return org.enrichment_status


def _token_match(email: str, first: str, last: str) -> bool:
    tokens = set(re.split(r"[._\-+\d]+", email.partition("@")[0].lower()))
    return any(len(w) >= 3 and w.lower() in tokens for w in (first, last))


def _store_contacts(session: Session, org: Organization, pages: list[tuple[Page, str, bool]], site: str,
                    stamp: datetime, counters: dict) -> None:
    people: dict[tuple[str, str], dict] = {}  # first page wins
    found: dict[str, dict] = {}  # one row per address per lead, first page wins
    for page, text, verified in pages:
        hits = extract_emails(page.html, text, site_domain=site, phone_verified=verified)
        blocked = suppressed_emails(session, {h.email for h in hits})
        base = {"organization_id": org.id, "source_key": SOURCE_KEY, "source_url": page.url, "collected_at": stamp}
        for p in extract_people(text):
            people.setdefault((p.first_name, p.last_name), {**base, "role": "staff", "first_name": p.first_name,
                                                            "last_name": p.last_name, "title": p.title})
        for h in hits:
            if h.email not in blocked:
                found.setdefault(h.email, base)
    rows = list(people.values())
    for email, base in found.items():
        # an address is attached only when its local part names the person; otherwise it is a general contact
        owner = next((r for r in rows if r["role"] == "staff" and "email" not in r
                      and _token_match(email, r["first_name"], r["last_name"])), None)
        if owner:
            owner.update(email=email, email_status="found_on_page")
        else:
            rows.append({**base, "role": "general", "first_name": "", "last_name": email, "title": None,
                         "email": email, "email_status": "found_on_page"})
    session.add_all(Contact(**r) for r in rows)
    session.flush()
    counters["emails_found"] += sum(1 for r in rows if r.get("email"))
    counters["people_found"] += len(people)


def _try_lead(session: Session, org: Organization, search, fetch, sleep) -> tuple[dict, str | None]:
    """Returns (counters, failure kind). Raises only SearchError(auth)."""
    for retry in (False, True):
        attempt: dict = {}
        try:
            if enrich_lead(session, org, search=search, fetch=fetch, counters=attempt) == "failed":
                return {}, "fetch"
            return attempt, None
        except SearchError as e:
            session.rollback()
            if e.kind == "auth":
                raise
            if e.kind == "rate_limited" and not retry:
                sleep(5)
                continue
            return {}, e.kind
        except FetchFailed:  # backstop: enrich_lead handles per-fetch failures itself
            session.rollback()
            return {}, "fetch"
        except Exception as e:  # noqa: BLE001 - one bad lead must not stall the job; type only, message may hold data
            session.rollback()
            return {}, type(e).__name__
    return {}, "rate_limited"


def _save_counters(session: Session, job_id: UUID, attempt: dict, fetch_stats: dict, seen: dict) -> None:
    job = session.get(SearchJob, job_id, populate_existing=True)
    counters = {k: 0 for k in COUNTERS} | dict(job.counters or {})
    for k, v in attempt.items():
        counters[k] += v
    for k, was in seen.items():
        counters[k] += fetch_stats.get(k, 0) - was
        seen[k] = fetch_stats.get(k, 0)
    job.counters = counters
    session.commit()


def enrich_job_leads(session_factory, job_id: UUID, *, search: Callable[[str], list[str]],
                     fetch: Callable[[str], Page | None], fetch_stats: dict, sleep: Callable[[float], None]) -> str:
    with session_factory() as session:
        ids = list(session.scalars(
            select(SearchJobLead.organization_id).join(Organization, Organization.id == SearchJobLead.organization_id)
            .where(SearchJobLead.search_job_id == job_id, Organization.enrichment_status.in_(("not_run", "failed")))
            .order_by(SearchJobLead.created_at, SearchJobLead.id, Organization.npi)))
        seen = {k: fetch_stats.get(k, 0) for k in ("pages_fetched", "blocked_by_robots", "skipped")}
        for org_id in ids:
            if session.get(SearchJob, job_id, populate_existing=True).cancel_requested:
                return "cancelled"
            org = session.get(Organization, org_id, populate_existing=True)
            try:
                attempt, failure = _try_lead(session, org, search, fetch, sleep)
            except SearchError:
                session.get(SearchJob, job_id, populate_existing=True).error = AUTH_MESSAGE
                _save_counters(session, job_id, {}, fetch_stats, seen)
                return "paused"
            if failure:
                logger.warning("enrich job %s: lead failed (%s)", job_id, failure)
                session.get(Organization, org_id, populate_existing=True).enrichment_status = "failed"
                attempt = {"enrich_attempted": 1, "enrich_failures": 1}
            _save_counters(session, job_id, attempt, fetch_stats, seen)
    return "done"
