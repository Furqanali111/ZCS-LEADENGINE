import copy
import json
from pathlib import Path

from sqlalchemy import func, select

from app.models import Contact, LeadScore, Location, Organization, SearchJob, SearchJobLead, SourceRecord
from app.services.search import run_job
from app.sources.npi_registry import SourceError, digits
from app.worker import claim_next, pause_running_jobs, run_next

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
    def fetch(client, *, enumeration_type, specialty, state, city, skip):
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


def test_never_requests_skip_above_1000(db, session_factory):
    # target_count is capped at 1200 by the schema, so inactive records keep both phases paging to the end
    inactive = copy.deepcopy(NPI2[0])
    inactive["basic"]["status"] = "D"
    full_page = [inactive] * 200
    calls = []

    def fetch(client, *, enumeration_type, specialty, state, city, skip):
        calls.append((enumeration_type, skip))
        return copy.deepcopy(full_page)

    job_id = make_job(db)
    run(session_factory, job_id, fetch)
    job = job_of(db, job_id)
    skips = [0, 200, 400, 600, 800, 1000]
    assert calls == [("NPI-2", s) for s in skips] + [("NPI-1", s) for s in skips]
    assert job.status == "completed"
    assert job.counters["skipped_inactive"] == 2400 and job.counters["pages_fetched"] == 12


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
