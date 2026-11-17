"""Per-lead website enrichment. Brave results live in memory only; only verified facts are stored."""
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Contact, Location, Organization, SearchJob, SearchJobLead
from app.services.leads import rescore_org
from app.services.maps import enrich_maps, maps_url, same_name
from app.services.suppression import suppressed_emails
from app.services.verify import (FALLBACK_PATHS, blocked_host, candidate_roots, extract_emails, extract_people, page_links,
                                 page_text, registrable_domain, relevant_links, verify_website)
from app.sources.brave import SearchError
from app.sources.gmaps import Listing
from app.sources.web import FetchFailed, Page

logger = logging.getLogger(__name__)

SOURCE_KEY = "practice_website"
SKIP = ("enriched", "rejected_by_user")
COUNTERS = ("enrich_attempted", "websites_found", "no_website_found", "emails_found", "people_found",
            "pages_fetched", "blocked_by_robots", "skipped", "enrich_failures")
AUTH_MESSAGE = "Brave Search rejected the API key. Check BRAVE_API_KEY and resume the job."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _maps_listing(session: Session, org: Organization, maps: Callable[[str], Listing | None]) -> Listing | None:
    """The lead's Google Maps listing, or None (no address, no match, blocked, browser trouble): the caller then searches the web."""
    url = maps_url(org, org.locations)
    if not url:
        return None
    try:
        listing = maps(url)
    except Exception:  # noqa: BLE001 - MapsBlocked or a browser failure must not fail the lead
        return None
    if listing and org.organization_type != "hospital" and not same_name(org, listing):
        return None  # a neighbouring tenant's listing: no website there says nothing about this practice
    # Only hospitals keep the Maps phone and hours: a medical building holds many practices, so a practice's listing may be a neighbour's.
    if listing and org.organization_type == "hospital" and org.maps_status != "matched":
        enrich_maps(session, org, lookup=lambda _: listing)
    return listing


def enrich_lead(session: Session, org: Organization, *, search: Callable[[str], list[str]],
                fetch: Callable[[str], Page | None], counters: dict, maps: Callable[[str], Listing | None] | None = None,
                now: Callable[[], datetime] = _now) -> str:
    if org.enrichment_status in SKIP:
        return org.enrichment_status
    for k in COUNTERS:
        counters.setdefault(k, 0)
    counters["enrich_attempted"] += 1
    stamp = now()

    query = " ".join(p for p in (org.name, org.city, org.state) if p)
    phones = [p for p in [org.phone, *session.scalars(select(Location.phone).where(Location.organization_id == org.id))] if p]

    listing = _maps_listing(session, org, maps) if maps else None
    # A Maps listing is the business's own entry: its website, or none. Only without a listing do we guess with a web search.
    urls = ([listing.website] if listing.website else []) if listing else search(query)
    roots = candidate_roots(urls)
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
        pages = [(home, text)]
        links = relevant_links(page_links(home.html, home.url), site) or [urljoin(home.url, p) for p in FALLBACK_PATHS]
        for url in links:
            if url == home.url:
                continue
            try:
                extra = fetch(url)
            except FetchFailed:  # keep what the home page produced
                continue
            if extra is not None:
                t = page_text(extra.html)
                pages.append((extra, t))
        org.website = f"{parts.scheme}://{parts.netloc}/"
        org.website_evidence = {"page_url": home.url, "check": check, "checked_at": stamp.isoformat()}
        org.enrichment_status = "enriched"
        counters["websites_found"] += 1
        _store_contacts(session, org, pages, stamp, counters)
    org.enriched_at = stamp
    rescore_org(session, org)
    return org.enrichment_status


def _token_match(email: str, first: str, last: str) -> bool:
    local = email.partition("@")[0].lower()
    tokens = set(re.split(r"[._\-+\d]+", local))
    if any(len(w) >= 3 and w.lower() in tokens for w in (first, last)):
        return True
    f, l = first.lower(), last.lower()  # joined forms: annboss, jsmith, johns
    return bool(f and l) and re.sub(r"[._\-+\d]", "", local) in {f + l, l + f, f[0] + l, f + l[0], l + f[0]}


def _store_contacts(session: Session, org: Organization, pages: list[tuple[Page, str]], stamp: datetime, counters: dict) -> None:
    people: dict[tuple[str, str], dict] = {}  # first page wins
    found: dict[str, dict] = {}  # one row per address per lead, first page wins
    for page, text in pages:
        hits = extract_emails(page.html, text)
        blocked = suppressed_emails(session, {h.email for h in hits})
        base = {"organization_id": org.id, "source_key": SOURCE_KEY, "source_url": page.url, "collected_at": stamp}
        for p in extract_people(text):
            people.setdefault((p.first_name, p.last_name), {**base, "role": "staff", "first_name": p.first_name,
                                                            "last_name": p.last_name, "title": p.title})
        for h in hits:
            if h.email not in blocked:
                found.setdefault(h.email, base)
    rows = list(people.values())
    # The NPI authorized official is often the owner or administrator: an address that names them is a decision-maker's.
    officials = [o for o in session.execute(select(Contact.first_name, Contact.last_name, Contact.title).where(
        Contact.organization_id == org.id, Contact.role == "authorized_official")) if (o.first_name, o.last_name) not in people]
    for email, base in found.items():
        # an address is attached only when its local part names the person; otherwise it is a general contact
        owner = next((r for r in rows if r["role"] == "staff" and "email" not in r
                      and _token_match(email, r["first_name"], r["last_name"])), None)
        official = None if owner else next((o for o in officials if _token_match(email, o.first_name or "", o.last_name or "")), None)
        if owner:
            owner.update(email=email, email_status="found_on_page")
        elif official:
            officials.remove(official)
            rows.append({**base, "role": "staff", "first_name": official.first_name, "last_name": official.last_name,
                         "title": official.title, "email": email, "email_status": "found_on_page"})
        else:
            rows.append({**base, "role": "general", "first_name": "", "last_name": email, "title": None,
                         "email": email, "email_status": "found_on_page"})
    session.add_all(Contact(**r) for r in rows)
    session.flush()
    counters["emails_found"] += sum(1 for r in rows if r.get("email"))
    counters["people_found"] += len(people)


def _try_lead(session: Session, org: Organization, search, fetch, sleep, maps=None) -> tuple[dict, str | None]:
    """Returns (counters, failure kind). Raises only SearchError(auth)."""
    for retry in (False, True):
        attempt: dict = {}
        try:
            if enrich_lead(session, org, search=search, fetch=fetch, counters=attempt, maps=maps) == "failed":
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
                     fetch: Callable[[str], Page | None], fetch_stats: dict, sleep: Callable[[float], None], maps=None) -> str:
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
                attempt, failure = _try_lead(session, org, search, fetch, sleep, maps)
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
