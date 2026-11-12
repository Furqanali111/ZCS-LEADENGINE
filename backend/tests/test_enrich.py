from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Contact, LeadScore, Organization, SearchJob, SearchJobLead, SourceRecord, SuppressionEntry
from app.services.enrich import enrich_job_leads, enrich_lead
from app.sources.brave import SearchError
from app.sources.web import FetchFailed, Page
from tests.test_api import add_lead
from tests.test_search import NPI2, make_job

NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)
SECRET = "BSA-secret-key"

HOME = """<html><body><h1>Lone Star Family Care, Austin</h1><p>Call (512) 555-0101 or other@gmail.com</p>
<a href="/team">Our Team</a><a href="/contact">Contact</a></body></html>"""
TEAM = """<html><body><p>Jane Doe, Practice Manager, jane@lonestar.example</p>
<p>Email info@lonestar.example</p></body></html>"""
CONTACT = "<html><body><p>Reach us at billing@lonestar.example or other@gmail.com</p></body></html>"


def site(pages: dict[str, str], calls: list | None = None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if url not in pages:
            return None
        return Page(url=url, html=pages[url])
    return fetch


GOOD = {"https://lonestar.example/": HOME, "https://lonestar.example/team": TEAM,
        "https://lonestar.example/contact": CONTACT}


def lead(db, **kw):
    org = add_lead(db, "1000000001", "Lone Star Family Care", 50, "medium", phone="512-555-0101", **kw)
    db.query(SourceRecord).filter_by(organization_id=org.id).update({"raw": NPI2[0]})
    db.commit()
    return org


def web_contacts(db, org):
    db.expire_all()
    return db.scalars(select(Contact).where(Contact.organization_id == org.id, Contact.source_key == "practice_website")).all()


def enrich(db, org, results=("https://lonestar.example/",), pages=GOOD, counters=None):
    queries = []

    def search(q):
        queries.append(q)
        return list(results)
    status = enrich_lead(db, org, search=search, fetch=site(pages), counters={} if counters is None else counters,
                         now=lambda: NOW)
    db.commit()
    return status, queries


def test_phone_match_stores_website_contacts_and_evidence(db):
    org = lead(db)
    counters = {}
    status, queries = enrich(db, org, counters=counters)
    assert status == "enriched"
    assert queries == ["Lone Star Family Care Austin TX"]
    db.refresh(org)
    assert org.website == "https://lonestar.example/"
    assert org.enriched_at == NOW
    assert set(org.website_evidence) == {"page_url", "check", "checked_at"}
    assert org.website_evidence["check"] == "phone"
    rows = {(c.role, c.first_name, c.last_name): c for c in web_contacts(db, org)}
    jane = rows[("staff", "Jane", "Doe")]
    assert (jane.title, jane.email, jane.email_status) == ("practice manager", "jane@lonestar.example", "found_on_page")
    assert jane.source_url == "https://lonestar.example/team" and jane.collected_at == NOW
    general = rows[("general", "", "info@lonestar.example")]
    assert general.email == "info@lonestar.example" and general.first_name == ""
    assert ("general", "", "other@gmail.com") in rows  # free mail accepted on a phone-verified site only
    assert counters["websites_found"] == 1 and counters["people_found"] == 1 and counters["emails_found"] == 4


def test_no_passing_candidate_stores_nothing(db):
    org = lead(db)
    status, _ = enrich(db, org, pages={"https://lonestar.example/": "<p>Some other business in Dallas</p>"})
    assert status == "no_website_found"
    db.refresh(org)
    assert org.website is None and org.website_evidence is None and org.enriched_at == NOW
    assert web_contacts(db, org) == []


def test_second_candidate_tried_when_first_fails(db):
    org = lead(db)
    pages = {"https://wrong.example/": "<p>Nothing relevant</p>", **GOOD}
    status, _ = enrich(db, org, results=["https://wrong.example/", "https://lonestar.example/"], pages=pages)
    assert status == "enriched"
    db.refresh(org)
    assert org.website == "https://lonestar.example/"


def test_suppressed_email_is_not_stored(db):
    org = lead(db)
    db.add(SuppressionEntry(kind="email", value="jane@lonestar.example"))
    db.commit()
    enrich(db, org)
    emails = {c.email for c in web_contacts(db, org)}
    assert "jane@lonestar.example" not in emails and "info@lonestar.example" in emails
    assert ("staff", "Jane", "Doe") in {(c.role, c.first_name, c.last_name) for c in web_contacts(db, org)}


def test_rerun_replaces_web_contacts_and_keeps_npi_contacts(db):
    org = lead(db)
    enrich(db, org)
    first = {(c.role, c.first_name, c.last_name) for c in web_contacts(db, org)}
    org.enrichment_status = "failed"
    db.commit()
    enrich(db, org)
    assert {(c.role, c.first_name, c.last_name) for c in web_contacts(db, org)} == first
    assert len(web_contacts(db, org)) == len(first)
    npi = db.scalars(select(Contact).where(Contact.organization_id == org.id, Contact.source_key == "npi_registry")).all()
    assert len(npi) == 2


def test_enriched_and_rejected_leads_are_skipped(db):
    org = lead(db)
    for state in ("enriched", "rejected_by_user"):
        org.enrichment_status = state
        db.commit()
        calls = []
        counters = {}
        assert enrich_lead(db, org, search=lambda q: calls.append(q) or [], fetch=site({}), counters=counters,
                           now=lambda: NOW) == state
        assert calls == [] and counters == {}


def test_rescore_counts_staff_with_title(db):
    org = lead(db)
    raw = {**NPI2[0], "basic": {k: v for k, v in NPI2[0]["basic"].items() if not k.startswith("authorized_official")}}
    db.query(SourceRecord).filter_by(organization_id=org.id).update({"raw": raw})
    db.commit()
    enrich(db, org)
    db.expire_all()
    dm = db.scalar(select(LeadScore).where(LeadScore.organization_id == org.id)).components["decision_maker"]
    assert dm["points"] > 0 and "website" in dm["reason"]


def test_no_source_record_skips_rescore(db):
    org = lead(db)
    db.query(SourceRecord).filter_by(organization_id=org.id).delete()
    db.commit()
    status, _ = enrich(db, org)
    assert status == "enriched"
    assert db.get(Organization, org.id).fit_score == 50


# ---- job loop ----

def link(db, job_id, *orgs):
    for o in orgs:
        db.add(SearchJobLead(search_job_id=job_id, organization_id=o.id, was_new=True))
        db.commit()  # separate transactions so created_at orders the leads


def run(session_factory, job_id, search, fetch=None, sleeps=None, stats=None):
    return enrich_job_leads(session_factory, job_id, search=search, fetch=fetch or site(GOOD),
                            fetch_stats=stats if stats is not None else {}, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def job(db, job_id):
    db.expire_all()
    return db.get(SearchJob, job_id)


def test_job_counts_and_commits_per_lead(db, session_factory):
    org = lead(db)
    jid = make_job(db, enrich=True)
    link(db, jid, org)
    stats = {"pages_fetched": 0, "blocked_by_robots": 0}

    def fetch(url):
        stats["pages_fetched"] += 1
        return site(GOOD)(url)
    assert run(session_factory, jid, lambda q: ["https://lonestar.example/"], fetch, stats=stats) == "done"
    c = job(db, jid).counters
    assert c["enrich_attempted"] == 1 and c["websites_found"] == 1 and c["pages_fetched"] == 3
    assert c["enrich_failures"] == 0 and c["blocked_by_robots"] == 0
    db.expire_all()
    assert db.get(Organization, org.id).enrichment_status == "enriched"


def test_fetch_failed_marks_failed_and_next_run_retries(db, session_factory):
    org = lead(db)
    jid = make_job(db, enrich=True)
    link(db, jid, org)

    def boom(url):
        raise FetchFailed("down")
    assert run(session_factory, jid, lambda q: ["https://lonestar.example/"], boom) == "done"
    db.expire_all()
    assert db.get(Organization, org.id).enrichment_status == "failed"
    assert job(db, jid).counters["enrich_failures"] == 1
    assert run(session_factory, jid, lambda q: ["https://lonestar.example/"]) == "done"
    db.expire_all()
    assert db.get(Organization, org.id).enrichment_status == "enriched"


def test_auth_error_pauses_without_leaking_key(db, session_factory, caplog):
    org = lead(db)
    jid = make_job(db, enrich=True)
    link(db, jid, org)

    def search(q):
        raise _leaky(SECRET)
    assert run(session_factory, jid, search) == "paused"
    j = job(db, jid)
    assert j.error and SECRET not in j.error
    assert SECRET not in str(j.counters) and SECRET not in caplog.text
    db.expire_all()
    assert db.get(Organization, org.id).enrichment_status == "not_run"


def _leaky(key):
    e = SearchError("auth")
    e.args = (f"rejected key {key}",)  # a message carrying the key must still never reach job.error or logs
    return e


def test_rate_limit_sleeps_and_retries_once(db, session_factory):
    org = lead(db)
    jid = make_job(db, enrich=True)
    link(db, jid, org)
    calls = []

    def search(q):
        calls.append(q)
        if len(calls) == 1:
            raise SearchError("rate_limited")
        return ["https://lonestar.example/"]
    sleeps = []
    assert run(session_factory, jid, search, sleeps=sleeps) == "done"
    assert sleeps == [5]
    c = job(db, jid).counters
    assert c["enrich_attempted"] == 1 and c["enrich_failures"] == 0
    db.expire_all()
    assert db.get(Organization, org.id).enrichment_status == "enriched"


def test_persistent_rate_limit_fails_the_lead(db, session_factory):
    org = lead(db)
    jid = make_job(db, enrich=True)
    link(db, jid, org)

    def search(q):
        raise SearchError("rate_limited")
    sleeps = []
    assert run(session_factory, jid, search, sleeps=sleeps) == "done"
    assert sleeps == [5]
    db.expire_all()
    assert db.get(Organization, org.id).enrichment_status == "failed"
    assert job(db, jid).counters["enrich_failures"] == 1


def test_cancel_between_leads_and_resume_skips_enriched(db, session_factory):
    a = lead(db)
    b = add_lead(db, "1000000002", "Other Clinic", 40, "low")
    jid = make_job(db, enrich=True)
    link(db, jid, a, b)
    seen = []

    def search(q):
        seen.append(q)
        db.query(SearchJob).filter_by(id=jid).update({"cancel_requested": True})
        db.commit()
        return ["https://lonestar.example/"]
    assert run(session_factory, jid, search) == "cancelled"
    assert len(seen) == 1
    db.expire_all()
    states = {db.get(Organization, o.id).enrichment_status for o in (a, b)}
    assert states == {"enriched", "not_run"} or states == {"no_website_found", "not_run"}  # whichever ran first
    done_first = next(o for o in (a, b) if db.get(Organization, o.id).enrichment_status != "not_run")
    other = b if done_first is a else a

    db.query(SearchJob).filter_by(id=jid).update({"cancel_requested": False})
    db.commit()
    resumed = []
    assert run(session_factory, jid, lambda q: resumed.append(q) or []) == "done"
    assert resumed == [" ".join(p for p in (other.name, other.city, other.state) if p)]  # the done lead was not repeated


def test_rejected_by_user_lead_is_skipped_in_job(db, session_factory):
    org = lead(db)
    org.enrichment_status = "rejected_by_user"
    jid = make_job(db, enrich=True)
    db.commit()
    link(db, jid, org)
    calls = []
    assert run(session_factory, jid, lambda q: calls.append(q) or []) == "done"
    assert calls == []


def test_stored_data_has_no_search_snippets(db):
    org = lead(db)
    enrich(db, org, results=["https://lonestar.example/?utm=Best-Doctor-Ever"])
    db.refresh(org)
    assert set(org.website_evidence) == {"page_url", "check", "checked_at"}
    assert "Best" not in str(org.website_evidence) and "utm" not in org.website


def contacts_by(db, org):
    return {(c.role, c.first_name, c.last_name): c for c in web_contacts(db, org)}


def test_email_goes_only_to_person_it_names(db):
    org = lead(db)
    team = "<p>Jane Doe, Practice Manager. John Roe, Owner, john@lonestar.example. jane@lonestar.example</p>"
    enrich(db, org, pages={**GOOD, "https://lonestar.example/team": team})
    rows = contacts_by(db, org)
    assert rows[("staff", "Jane", "Doe")].email == "jane@lonestar.example"
    assert rows[("staff", "John", "Roe")].email == "john@lonestar.example"
    emails = [c.email for c in web_contacts(db, org) if c.email]
    assert len(emails) == len(set(emails))


def test_unrelated_address_is_general_and_whole_token_only(db):
    org = lead(db)
    team = "<p>Ann Lee, Owner</p><p>mail leeds@lonestar.example</p><p>lee.ann@lonestar.example</p>"
    enrich(db, org, pages={**GOOD, "https://lonestar.example/team": team})
    rows = contacts_by(db, org)
    assert rows[("staff", "Ann", "Lee")].email == "lee.ann@lonestar.example"
    assert rows[("general", "", "leeds@lonestar.example")].email == "leeds@lonestar.example"


def test_address_not_stored_twice_across_pages(db):
    org = lead(db)
    contact = "<p>jane@lonestar.example</p>"
    enrich(db, org, pages={**GOOD, "https://lonestar.example/contact": contact})
    emails = [c.email for c in web_contacts(db, org) if c.email]
    assert emails.count("jane@lonestar.example") == 1


def test_name_city_site_rejects_free_and_foreign_mail(db):
    org = lead(db)
    home = "<p>Lone Star Family Care in Austin. info@lonestar.example other@gmail.com x@elsewhere.org</p>"
    enrich(db, org, pages={"https://lonestar.example/": home})
    db.refresh(org)
    assert org.website_evidence["check"] == "name_city"
    assert {c.email for c in web_contacts(db, org)} == {"info@lonestar.example"}


def test_mid_lead_extra_page_failure_keeps_the_lead(db, session_factory):
    a = lead(db)
    b = add_lead(db, "1000000002", "Other Clinic", 40, "low")
    db.query(SourceRecord).filter_by(organization_id=b.id).update({"raw": NPI2[0]})
    db.commit()
    jid = make_job(db, enrich=True)
    link(db, jid, a, b)
    pages = {**GOOD, "https://other.example/": "<p>Other Clinic Austin</p><a href='/team'>Team</a>"}
    ok = site(pages)

    def fetch(url):
        if url == "https://other.example/team":
            raise FetchFailed("down")
        return ok(url)
    searches = iter([["https://lonestar.example/"], ["https://other.example/"]])
    assert run(session_factory, jid, lambda q: next(searches), fetch) == "done"
    db.expire_all()
    assert db.get(Organization, a.id).enrichment_status == "enriched" and web_contacts(db, a)
    assert db.get(Organization, b.id).enrichment_status == "enriched"
    assert db.get(Organization, b.id).website == "https://other.example/"


def test_unexpected_error_fails_only_that_lead(db, session_factory, caplog):
    a = lead(db)
    b = add_lead(db, "1000000002", "Other Clinic", 40, "low")
    jid = make_job(db, enrich=True)
    link(db, jid, a, b)
    n = []

    def search(q):
        n.append(q)
        if len(n) == 1:
            raise RuntimeError("secret detail")
        return []
    assert run(session_factory, jid, search) == "done"
    db.expire_all()
    assert db.get(Organization, a.id).enrichment_status == "failed"
    assert db.get(Organization, b.id).enrichment_status == "no_website_found"
    assert job(db, jid).counters["enrich_failures"] == 1
    assert "secret detail" not in caplog.text and "RuntimeError" in caplog.text


# ---- final fix wave ----

def dead(*urls, pages=GOOD):
    ok = site(pages)

    def fetch(url):
        if url in urls:
            raise FetchFailed("down")
        return ok(url)
    return fetch


def test_dead_first_root_does_not_fail_lead(db):
    org = lead(db)
    status = enrich_lead(db, org, search=lambda q: ["https://dead.example/", "https://lonestar.example/"],
                         fetch=dead("https://dead.example/"), counters={}, now=lambda: NOW)
    assert status == "enriched" and org.website == "https://lonestar.example/"


def test_dead_extra_page_keeps_home_contacts(db):
    org = lead(db)
    status = enrich_lead(db, org, search=lambda q: ["https://lonestar.example/"],
                         fetch=dead("https://lonestar.example/team"), counters={}, now=lambda: NOW)
    db.commit()
    assert status == "enriched"
    assert "billing@lonestar.example" in {c.email for c in web_contacts(db, org)}


def test_all_roots_dead_marks_failed_and_keeps_old_contacts(db):
    org = lead(db)
    enrich(db, org)
    before = len(web_contacts(db, org))
    org.enrichment_status = "failed"
    db.commit()
    counters = {}
    status = enrich_lead(db, org, search=lambda q: ["https://a.example/", "https://b.example/"],
                         fetch=dead("https://a.example/", "https://b.example/"), counters=counters, now=lambda: NOW)
    db.commit()
    assert status == "failed" and org.enrichment_status == "failed"
    assert len(web_contacts(db, org)) == before


def test_reachable_but_unverified_root_is_no_website_found(db):
    org = lead(db)
    pages = {"https://other.example/": "<p>Nothing</p>"}
    status = enrich_lead(db, org, search=lambda q: ["https://dead.example/", "https://other.example/"],
                         fetch=dead("https://dead.example/", pages=pages), counters={}, now=lambda: NOW)
    assert status == "no_website_found"


def test_job_counts_dead_lead_as_failure_and_retries(db, session_factory):
    org = lead(db)
    jid = make_job(db, enrich=True)
    link(db, jid, org)
    assert run(session_factory, jid, lambda q: ["https://lonestar.example/"], dead("https://lonestar.example/")) == "done"
    db.expire_all()
    assert db.get(Organization, org.id).enrichment_status == "failed"
    assert job(db, jid).counters["enrich_failures"] == 1


def test_redirect_to_blocked_host_is_not_stored(db):
    org = lead(db)
    ok = site(GOOD)

    def fetch(url):
        return Page("https://www.yelp.com/biz/lone-star", HOME) if url == "https://lonestar.example/" else ok(url)
    status = enrich_lead(db, org, search=lambda q: ["https://lonestar.example/"], fetch=fetch, counters={}, now=lambda: NOW)
    assert status == "no_website_found" and org.website is None


def test_skipped_counter_is_summed_into_job(db, session_factory):
    org = lead(db)
    jid = make_job(db, enrich=True)
    link(db, jid, org)
    stats = {"pages_fetched": 0, "blocked_by_robots": 0, "skipped": 0}

    def fetch(url):
        stats["skipped"] += 1
        return site(GOOD)(url)
    run(session_factory, jid, lambda q: ["https://lonestar.example/"], fetch, stats=stats)
    assert job(db, jid).counters["skipped"] == 3
