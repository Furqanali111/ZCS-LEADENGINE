import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import delete, event, func, select, update

from app.models import (
    Contact, LeadScore, Location, Organization, SearchJob, SearchJobLead, SearchProgress, SourceConfig, SourceRecord,
)
from app.services.search import run_job
from app.sources.npi_registry import SourceError, digits
from app.worker import claim_next, pause_running_jobs, run_next

pytestmark = pytest.mark.usefixtures("npi_source")
FIXTURES = Path(__file__).parent / "fixtures"
NPI2 = json.loads((FIXTURES / "npi2_page.json").read_text(encoding="utf-8"))["results"]
NPI1 = json.loads((FIXTURES / "npi1_page.json").read_text(encoding="utf-8"))["results"]


def many(n: int, start: int = 1900000000) -> list[dict]:
    """n distinct practice records cloned from the NPI-2 fixture."""
    out = []
    for i in range(n):
        r = copy.deepcopy(NPI2[i % len(NPI2)])
        r["number"] = start + i
        out.append(r)
    return out


def fake(pages: dict[str, list[list[dict]]], calls: list | None = None):
    def fetch(client, *, enumeration_type, specialty, state, city, skip, zip_prefix=""):
        if calls is not None:
            calls.append((enumeration_type, skip))
        type_pages = pages.get(enumeration_type, [])
        i = skip // 200
        return copy.deepcopy(type_pages[i]) if i < len(type_pages) else []
    return fetch


def make_job(db, **kw) -> object:
    job = SearchJob(**{"specialty": "Internal Medicine", "state": "TX", "target_count": 1200,
                       "sources": ["npi_registry"], **kw})
    db.add(job)
    db.commit()
    return job.id


def run(session_factory, job_id, fetch, sleeps: list | None = None):
    run_job(session_factory, job_id, fetch=fetch, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def job_of(db, job_id) -> SearchJob:
    db.expire_all()
    return db.get(SearchJob, job_id)


def count(db, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_job_saves_orgs_scores_and_links(db, session_factory):
    job_id = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, job_id, fake({"NPI-2": [NPI2]}))
    job = job_of(db, job_id)
    assert job.status == "completed"
    assert job.started_at and job.finished_at and job.error is None
    assert job.counters["accepted_new"] == 20 and job.counters["candidates_seen"] == 20
    assert job.counters["pages_fetched"] == 1
    assert count(db, Organization) == 20
    assert count(db, SearchJobLead, SearchJobLead.search_job_id == job_id, SearchJobLead.was_new.is_(True)) == 20
    assert count(db, SourceRecord, SourceRecord.source_key == "npi_registry") == 20
    assert count(db, LeadScore) == 20
    assert count(db, Location) > 0 and count(db, Contact) > 0
    for org in db.scalars(select(Organization)):
        assert org.fit_score == org.score.total and org.priority == org.score.priority
        assert org.score.config_version and org.score.components["specialty"]["reason"]
        assert org.crm_status == "new"


def test_target_stops_job(db, session_factory):
    job_id = make_job(db, include_solo=False, include_subparts=True, target_count=5)
    run(session_factory, job_id, fake({"NPI-2": [NPI2]}))
    job = job_of(db, job_id)
    assert job.status == "completed"
    assert count(db, SearchJobLead, SearchJobLead.search_job_id == job_id) == 5
    assert job.counters["accepted_new"] == 5 and job.counters["candidates_seen"] == 5


def test_replaying_a_page_creates_no_duplicates(db, session_factory):
    fetch = fake({"NPI-2": [NPI2]})
    first = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, first, fetch)
    orgs, locs, contacts = count(db, Organization), count(db, Location), count(db, Contact)
    db.execute(delete(SearchProgress))  # start over, so the second search reads the same records again
    db.commit()
    second = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, second, fetch)
    a, b = job_of(db, first), job_of(db, second)
    assert b.status == "completed"
    assert (count(db, Organization), count(db, Location), count(db, Contact)) == (orgs, locs, contacts)
    assert b.counters["accepted_existing"] == a.counters["accepted_new"] == 20
    assert b.counters["accepted_new"] == 0 and b.counters["source_failures"] == 0
    assert count(db, SearchJobLead, SearchJobLead.search_job_id == second, SearchJobLead.was_new.is_(False)) == 20


def test_same_record_twice_and_repeated_address_cause_no_integrity_error(db, session_factory):
    rec = copy.deepcopy(NPI2[0])
    loc = next(a for a in rec["addresses"] if a["address_purpose"] == "LOCATION")
    rec["addresses"].append(copy.deepcopy(loc))  # same purpose, address_1 and zip twice in one lead
    blank = copy.deepcopy(loc)
    blank["address_1"], blank["postal_code"], blank["address_purpose"] = None, None, "MAILING"
    rec["addresses"] += [blank, copy.deepcopy(blank)]  # None address_1 and zip are stored as ''
    job_id = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, job_id, fake({"NPI-2": [[rec, copy.deepcopy(rec)]]}))
    job = job_of(db, job_id)
    assert job.status == "completed" and job.counters["source_failures"] == 0
    assert count(db, Organization) == 1
    assert count(db, SearchJobLead) == 1
    assert count(db, Location, Location.address_1 == "", Location.zip == "") == 1


def test_rerun_keeps_crm_status(db, session_factory):
    fetch = fake({"NPI-2": [NPI2]})
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fetch)
    org = db.scalars(select(Organization)).first()
    org.crm_status, org.name = "called", "Edited Locally"
    stamp = db.scalar(select(func.now()))
    org.status_updated_at = stamp
    db.commit()
    db.execute(delete(SearchProgress))
    db.commit()
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fetch)
    db.expire_all()
    org = db.get(Organization, org.id)
    assert org.crm_status == "called" and org.status_updated_at == stamp
    assert org.name != "Edited Locally"  # data fields are refreshed from the source


def test_excluded_subparts_counted(db, session_factory):
    job_id = make_job(db, include_solo=False, include_subparts=False)
    run(session_factory, job_id, fake({"NPI-2": [NPI2]}))
    job = job_of(db, job_id)
    assert count(db, Organization, Organization.organization_type == "subpart") == 0
    assert job.counters["skipped_excluded"] == 2
    assert job.counters["accepted_new"] == 18


def test_records_outside_us_states_skipped(db, session_factory):
    page = copy.deepcopy(NPI2[:3])
    for a in page[0]["addresses"]:
        a["state"] = "PR"
    page[1]["addresses"] = []  # no location, so no state
    job_id = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, job_id, fake({"NPI-2": [page]}))
    job = job_of(db, job_id)
    assert job.counters["skipped_excluded"] == 2 and job.counters["source_failures"] == 0
    assert count(db, Organization) == 1


def test_solo_phase_keeps_only_sole_proprietors(db, session_factory):
    job_id = make_job(db, include_practices=False)
    calls = []
    run(session_factory, job_id, fake({"NPI-1": [NPI1]}, calls))
    job = job_of(db, job_id)
    assert calls == [("NPI-1", 0)]
    assert job.status == "completed"
    assert job.counters["skipped_not_sole_proprietor"] == 14 and job.counters["accepted_new"] == 6
    types = set(db.scalars(select(Organization.organization_type)))
    assert types == {"solo_provider"}
    assert set(db.scalars(select(Contact.role))) == {"provider"}


def test_solo_skipped_when_phone_matches_known_org(db, session_factory):
    doctor = next(r for r in NPI1 if r["basic"].get("sole_proprietor") == "YES")
    phone = digits(next(a for a in doctor["addresses"] if a["address_purpose"] == "LOCATION")["telephone_number"])
    db.add(Organization(npi="1999999999", name="Big Clinic", organization_type="practice", state="TX",
                        phone=f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"))
    db.commit()
    job_id = make_job(db, include_practices=False)
    run(session_factory, job_id, fake({"NPI-1": [NPI1]}))
    job = job_of(db, job_id)
    assert job.counters["skipped_works_at_known_org"] >= 1
    assert count(db, Organization, Organization.npi == str(doctor["number"])) == 0


def test_cap_hit_splits_by_zip_prefix_and_never_requests_skip_above_1000(db, session_factory):
    # target_count allows more than the 1,200 cap, so inactive records keep both phases going; a capped whole-state
    # query is then split into the 100 two-digit ZIP prefixes (empty here)
    inactive = copy.deepcopy(NPI2[0])
    inactive["basic"]["status"] = "D"
    calls = []

    def fetch(client, *, enumeration_type, specialty, state, city, skip, zip_prefix=""):
        calls.append((enumeration_type, zip_prefix, skip))
        return [copy.deepcopy(inactive) for _ in range(200)] if not zip_prefix else []

    job_id = make_job(db)
    run(session_factory, job_id, fetch)
    job = job_of(db, job_id)
    whole_state = [("", s) for s in [0, 200, 400, 600, 800, 1000]]
    prefixes = [(f"{d:02d}", 0) for d in range(100)]
    assert [(p, s) for t, p, s in calls if t == "NPI-2"] == whole_state + prefixes
    assert [(p, s) for t, p, s in calls if t == "NPI-1"] == whole_state + prefixes
    assert max(s for _, _, s in calls) == 1000
    assert job.status == "completed"
    assert job.counters["skipped_inactive"] == 2400 and job.counters["pages_fetched"] == 212


def test_second_search_continues_after_the_first_instead_of_repeating_it(db, session_factory):
    records = many(400)
    calls = []

    def fetch(client, *, enumeration_type, specialty, state, city, skip, zip_prefix=""):
        calls.append((enumeration_type, skip))
        return copy.deepcopy(records[skip:skip + 200])

    first = make_job(db, include_solo=False, target_count=150)
    run(session_factory, first, fetch)
    stopped_at = db.scalar(select(SearchProgress)).cursor["practices"]["skip"]  # excluded records are consumed too
    assert stopped_at >= 150
    second = make_job(db, include_solo=False, target_count=150)
    run(session_factory, second, fetch)
    a, b = job_of(db, first), job_of(db, second)
    assert a.counters["accepted_new"] == 150 and b.counters["accepted_new"] == 150
    assert calls == [("NPI-2", 0), ("NPI-2", stopped_at)]  # the second search starts where the first stopped
    assert count(db, Organization) == 300
    assert db.scalar(select(SearchProgress.leads_fetched)) == 300


def test_finished_search_reads_nothing_new(db, session_factory):
    calls = []
    fetch = fake({"NPI-2": [NPI2]}, calls)
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fetch)
    again = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, again, fetch)
    assert len(calls) == 1  # the second search found the phase already walked to the end
    job = job_of(db, again)
    assert job.status == "completed" and job.counters.get("accepted_new", 0) == 0


def test_cancel_between_pages(db, session_factory):
    job_id = make_job(db, include_subparts=True)
    calls = []

    def fetch(client, **kw):
        calls.append(kw["skip"])
        with session_factory() as s:
            s.get(SearchJob, job_id).cancel_requested = True
            s.commit()
        return many(200)

    run(session_factory, job_id, fetch)
    job = job_of(db, job_id)
    assert calls == [0]
    assert job.status == "cancelled" and job.finished_at
    assert job.checkpoint == {"phase": "practices", "skip": 200}
    assert count(db, SearchJobLead) == 200


def test_cancelled_while_queued_never_runs(db, session_factory):
    job_id = make_job(db, cancel_requested=True)
    calls = []
    run(session_factory, job_id, fake({"NPI-2": [NPI2]}, calls))
    job = job_of(db, job_id)
    assert calls == [] and job.status == "cancelled" and job.finished_at


def test_fetch_failure_fails_job_then_resume_completes(db, session_factory):
    pages = {"NPI-2": [many(200), NPI2]}
    calls, sleeps = [], []
    working = fake(pages, calls)

    def flaky(client, **kw):
        if kw["skip"] == 200:
            calls.append(("NPI-2", 200))
            raise SourceError("NPI Registry returned HTTP 503")
        return working(client, **kw)

    job_id = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, job_id, flaky, sleeps)
    job = job_of(db, job_id)
    assert job.status == "failed" and "503" in job.error and job.finished_at
    assert job.checkpoint == {"phase": "practices", "skip": 200}
    assert calls.count(("NPI-2", 200)) == 4
    assert sleeps[-3:] == [1, 2, 4]
    assert count(db, Organization) == 200

    job.status = "queued"
    db.commit()
    calls.clear()
    run(session_factory, job_id, working)
    job = job_of(db, job_id)
    assert calls == [("NPI-2", 200)]
    assert job.status == "completed" and job.error is None
    assert count(db, Organization) == 220
    assert count(db, SearchJobLead, SearchJobLead.search_job_id == job_id) == 220
    assert job.counters["accepted_new"] == 220 and job.counters["pages_fetched"] == 2


def test_bad_record_is_skipped_not_fatal(db, session_factory):
    page = copy.deepcopy(NPI2)
    del page[3]["number"]
    job_id = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, job_id, fake({"NPI-2": [page]}))
    job = job_of(db, job_id)
    assert job.status == "completed"
    assert job.counters["source_failures"] == 1 and job.counters["accepted_new"] == 19
    assert count(db, Organization) == 19


def test_zero_results_completes_empty(db, session_factory):
    job_id = make_job(db)
    calls = []
    run(session_factory, job_id, fake({}, calls))
    job = job_of(db, job_id)
    assert calls == [("NPI-2", 0), ("NPI-1", 0)]
    assert job.status == "completed" and count(db, SearchJobLead) == 0


def test_pause_running_jobs(db):
    running = make_job(db, status="running")
    queued = make_job(db)
    assert pause_running_jobs(db) == 1
    assert job_of(db, running).status == "paused"
    assert job_of(db, queued).status == "queued"


def test_claim_takes_oldest_queued_job_once(db, session_factory):
    first = make_job(db)
    second = make_job(db)
    make_job(db, status="paused")
    assert claim_next(session_factory) == first
    assert claim_next(session_factory) == second
    assert claim_next(session_factory) is None
    assert job_of(db, first).status == "running"


def test_worker_marks_crashed_job_failed(db, session_factory, monkeypatch):
    job_id = make_job(db)

    def boom(*a, **kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("app.worker.run_job", boom)
    assert run_next(session_factory) is True
    job = job_of(db, job_id)
    assert job.status == "failed" and job.error == "RuntimeError" and job.finished_at
    assert run_next(session_factory) is False


def test_start_worker_runs_queued_job_in_daemon_thread(db, session_factory, monkeypatch):
    import time

    from app.worker import start_worker

    monkeypatch.setattr("app.worker.run_job", lambda sf, job_id: None)
    job_id = make_job(db)
    thread = start_worker(session_factory, poll_seconds=0.05)
    try:
        assert thread.daemon
        for _ in range(100):
            if job_of(db, job_id).status == "running":
                break
            time.sleep(0.05)
        assert job_of(db, job_id).status == "running"  # claimed; the stubbed run_job leaves it as is
    finally:
        thread.stop_event.set()
        thread.join(timeout=5)
    assert not thread.is_alive()


# ---- batched page writes -------------------------------------------------------------------------------------------


@pytest.fixture
def slow_path_calls(monkeypatch):
    """Records every NPI that goes through the per-record fallback (_save_lead)."""
    from app.services import search

    calls, original = [], search._save_lead

    def spy(session, job, lead, config):
        calls.append(lead.npi)
        return original(session, job, lead, config)

    monkeypatch.setattr(search, "_save_lead", spy)
    return calls


def statements_for_one_page(db, db_engine, session_factory, n: int, start: int) -> int:
    statements = []
    db.execute(delete(SearchProgress))  # every measurement is a first search
    db.commit()

    def listener(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", listener)
    try:
        run(session_factory, make_job(db, include_solo=False, include_subparts=True), fake({"NPI-2": [many(n, start)]}))
    finally:
        event.remove(db_engine, "before_cursor_execute", listener)
    return len(statements)


def test_page_round_trips_are_few_and_flat(db, db_engine, session_factory, slow_path_calls):
    # Round-trip proxy: the whole run (claim, page, checkpoint, commits, SAVEPOINT/RELEASE included) for one page.
    # The old per-record code needed about 2000 statements for 200 records. Bound 40 leaves headroom over the batched count.
    small = statements_for_one_page(db, db_engine, session_factory, 50, 1900000000)
    big = statements_for_one_page(db, db_engine, session_factory, 200, 1910000000)
    print("statements: 50 records =", small, "200 records =", big)
    assert big < 40
    # The extra 100-lead chunk costs 13 statements (SAVEPOINT/RELEASE, the batched upserts, the suppression enforce select);
    # a full 200-record page also reads one more, empty page, which costs 2 (known-NPI lookup and the cursor write).
    assert big - small == 15
    assert slow_path_calls == []
    assert count(db, Organization) == 250


def test_one_bad_record_falls_back_and_saves_the_rest(db, session_factory, slow_path_calls):
    page = many(30)
    page[7]["basic"]["organization_name"] = "Bad\x00Name"  # Postgres rejects NUL bytes, so the batched insert fails
    job_id = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, job_id, fake({"NPI-2": [page]}))
    job = job_of(db, job_id)
    assert job.status == "completed"
    assert job.counters["source_failures"] == 1 and job.counters["accepted_new"] == 29
    assert count(db, Organization) == 29 and count(db, LeadScore) == 29
    assert len(slow_path_calls) == 30  # the accepted set was retried one by one


def test_batched_rerun_keeps_crm_status_and_creates_no_duplicates(db, session_factory, slow_path_calls):
    fetch = fake({"NPI-2": [many(30)]})
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fetch)
    org = db.scalars(select(Organization)).first()
    org.crm_status, org.name = "called", "Edited Locally"
    db.commit()
    models = (Organization, Location, Contact, LeadScore, SourceRecord)
    sizes = [count(db, m) for m in models]
    db.execute(delete(SearchProgress))  # start over, so the rerun reads the same records
    db.commit()
    second = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, second, fetch)
    db.expire_all()
    assert [count(db, m) for m in models] == sizes
    assert db.get(Organization, org.id).crm_status == "called" and db.get(Organization, org.id).name != "Edited Locally"
    job = job_of(db, second)
    assert job.counters["accepted_existing"] == 30 and job.counters["accepted_new"] == 0
    assert count(db, SearchJobLead, SearchJobLead.search_job_id == second, SearchJobLead.was_new.is_(False)) == 30
    for o in db.scalars(select(Organization)):
        assert o.fit_score == o.score.total and o.priority == o.score.priority
    assert slow_path_calls == []


def test_repeated_addresses_within_and_across_leads_in_one_batch(db, session_factory, slow_path_calls):
    page = many(5)
    loc = next(a for a in page[0]["addresses"] if a["address_purpose"] == "LOCATION")
    page[0]["addresses"].append(copy.deepcopy(loc))  # repeated inside one lead
    for r in page[1:]:
        r["addresses"] = copy.deepcopy(page[0]["addresses"])  # same addresses on other leads in the page
    page.append(copy.deepcopy(page[2]))  # the same NPI twice in a page
    job_id = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, job_id, fake({"NPI-2": [page]}))
    job = job_of(db, job_id)
    assert job.status == "completed" and job.counters["source_failures"] == 0
    assert job.counters["accepted_new"] == 5 and job.counters["candidates_seen"] == 6
    assert count(db, Organization) == 5 and count(db, SearchJobLead) == 5
    assert slow_path_calls == []


def test_rerun_replaces_changed_authorized_official(db, session_factory):
    fetch = fake({"NPI-2": [NPI2]})
    run(session_factory, make_job(db, include_solo=False, include_subparts=True, include_hospitals=True), fetch)
    org = db.scalars(select(Organization)).first()
    old = db.scalars(select(Contact).where(Contact.organization_id == org.id)).all()
    assert old
    changed = copy.deepcopy(NPI2)
    for r in changed:
        r["basic"]["authorized_official_first_name"] = "Zed"
        r["basic"]["authorized_official_last_name"] = "Newperson"
    db.execute(delete(SearchProgress))
    db.commit()
    run(session_factory, make_job(db, include_solo=False, include_subparts=True, include_hospitals=True), fake({"NPI-2": [changed]}))
    db.expire_all()
    names = {c.first_name for c in db.scalars(select(Contact).where(Contact.organization_id == org.id))}
    assert names == {"Zed"}


def test_job_fails_when_source_not_available(db, session_factory):
    db.execute(update(SourceConfig).where(SourceConfig.key == "npi_registry").values(status="not_reviewed"))
    db.commit()
    job_id = make_job(db)
    run(session_factory, job_id, fake({"NPI-2": [NPI2]}))
    assert job_of(db, job_id).status == "failed"
    assert count(db, Organization) == 0


# ---- enrichment phase ----

@pytest.fixture
def enrich_sources(db):
    db.add_all([SourceConfig(key=k, name=k, status="available") for k in ("brave_search", "practice_websites")])
    db.commit()


def deps(search=None):
    from app.services.search import EnrichDeps
    return EnrichDeps(search=search or (lambda q: []), fetch=lambda url: None, fetch_stats={})


def run_enrich(session_factory, job_id, fetch, enrich_deps):
    run_job(session_factory, job_id, fetch=fetch, sleep=lambda s: None, enrich_deps=enrich_deps)


def test_enrich_job_runs_npi_then_enriches_linked_leads(db, session_factory, enrich_sources):
    job_id = make_job(db, include_solo=False, enrich=True)
    run_enrich(session_factory, job_id, fake({"NPI-2": [NPI2]}), deps())
    job = job_of(db, job_id)
    assert job.status == "completed" and job.error is None
    n = count(db, Organization, Organization.enrichment_status == "no_website_found")  # suppressed leads are not enriched
    assert n > 0 and job.counters["accepted_new"] == n and job.counters["pages_fetched"] == 1
    assert job.counters["enrich_attempted"] == job.counters["no_website_found"] == n


def test_enrich_false_never_touches_enrichment(db, session_factory):
    job_id = make_job(db, include_solo=False, include_subparts=True, include_hospitals=True)
    run_enrich(session_factory, job_id, fake({"NPI-2": [NPI2]}), deps(lambda q: 1 / 0))
    job = job_of(db, job_id)
    assert job.status == "completed" and job.counters["enrich_attempted"] == 0
    assert count(db, Organization, Organization.enrichment_status != "not_run") == 0


def test_resumed_enrich_phase_makes_no_npi_calls_and_skips_done_leads(db, session_factory, enrich_sources):
    job_id = make_job(db, include_solo=False, enrich=True)
    run_enrich(session_factory, job_id, fake({"NPI-2": [NPI2]}), deps())
    n = job_of(db, job_id).counters["enrich_attempted"]
    db.scalars(select(Organization).where(Organization.enrichment_status == "no_website_found").limit(1)).first().enrichment_status = "not_run"
    db.execute(update(SearchJob).where(SearchJob.id == job_id).values(status="queued", checkpoint={"phase": "enrich"}))
    db.commit()
    calls = []
    run_enrich(session_factory, job_id, fake({"NPI-2": [NPI2]}, calls), deps())
    job = job_of(db, job_id)
    assert calls == [] and job.status == "completed"
    assert job.counters["enrich_attempted"] == n + 1


def test_enrich_auth_error_pauses_job_with_message(db, session_factory, enrich_sources):
    from app.sources.brave import SearchError

    def bad(q):
        raise SearchError("auth")

    job_id = make_job(db, include_solo=False, enrich=True)
    run_enrich(session_factory, job_id, fake({"NPI-2": [NPI2]}), deps(bad))
    job = job_of(db, job_id)
    assert job.status == "paused" and "BRAVE_API_KEY" in job.error
    assert job.checkpoint == {"phase": "enrich"}


def test_cancel_during_enrichment_ends_cancelled(db, session_factory, enrich_sources):
    job_id = make_job(db, include_solo=False, enrich=True)

    def cancel(q):
        with session_factory() as s:
            s.execute(update(SearchJob).where(SearchJob.id == job_id).values(cancel_requested=True))
            s.commit()
        return []

    run_enrich(session_factory, job_id, fake({"NPI-2": [NPI2]}), deps(cancel))
    job = job_of(db, job_id)
    assert job.status == "cancelled" and job.counters["enrich_attempted"] == 1


def test_enrich_job_fails_when_enrich_source_not_available(db, session_factory, enrich_sources):
    db.execute(update(SourceConfig).where(SourceConfig.key == "brave_search").values(status="not_reviewed"))
    db.commit()
    job_id = make_job(db, enrich=True)
    run_enrich(session_factory, job_id, fake({"NPI-2": [NPI2]}), deps())
    job = job_of(db, job_id)
    assert job.status == "failed" and "brave_search" in job.error
    assert count(db, Organization) == 0


def _staffed_record():
    rec = copy.deepcopy(NPI2[0])
    rec["basic"] = {k: v for k, v in rec["basic"].items() if not k.startswith("authorized_official")}
    return rec


@pytest.mark.parametrize("batched", [True, False])
def test_research_keeps_staff_points_of_enriched_lead(db, session_factory, monkeypatch, batched):
    from app.services import search as search_mod
    from app.services.leads import rescore_org

    if not batched:
        def boom(*a, **k):
            raise RuntimeError("force record by record")
        monkeypatch.setattr(search_mod, "_save_batch", boom)
    rec = _staffed_record()
    run(session_factory, make_job(db, include_solo=False, include_subparts=True, include_hospitals=True), fake({"NPI-2": [[rec]]}))
    org = db.scalar(select(Organization))
    db.add(Contact(organization_id=org.id, role="staff", first_name="Ann", last_name="Lee", title="practice manager",
                   source_key="practice_website"))
    db.commit()
    rescore_org(db, org)
    db.commit()
    before = (org.fit_score, org.score.components["decision_maker"]["points"])
    assert before[1] > 0
    run(session_factory, make_job(db, include_solo=False, include_subparts=True, include_hospitals=True), fake({"NPI-2": [[rec]]}))
    db.expire_all()
    org = db.scalar(select(Organization))
    assert (org.fit_score, org.score.components["decision_maker"]["points"]) == before
    assert org.fit_score == org.score.total


def test_real_deps_use_separate_clients_and_key_only_goes_to_brave(db, session_factory, enrich_sources, monkeypatch):
    import httpx
    from app.services import search as search_mod

    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.host, req.headers.get("x-subscription-token")))
        if req.url.host == "api.search.brave.com":
            return httpx.Response(200, json={"web": {"results": [{"url": "https://practice.example/"}]}})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>hello</p>")

    clients = []

    def fake_client():
        clients.append(httpx.Client(transport=httpx.MockTransport(handler)))
        return clients[-1]
    real = search_mod.get_settings()
    monkeypatch.setattr(search_mod, "make_client", fake_client)
    monkeypatch.setattr(search_mod, "get_settings",
                        lambda: real.model_copy(update={"brave_api_key": "KEY123", "enrich_page_delay_seconds": 0}))
    job_id = make_job(db, include_solo=False, enrich=True, target_count=1)
    run_job(session_factory, job_id, fetch=fake({"NPI-2": [NPI2]}), sleep=lambda s: None)
    assert len(clients) == 2 and clients[0] is not clients[1] and all(c.is_closed for c in clients)
    brave_calls = [k for h, k in seen if h == "api.search.brave.com"]
    page_calls = [k for h, k in seen if h != "api.search.brave.com"]
    assert brave_calls == ["KEY123"] and page_calls and all(k is None for k in page_calls)
