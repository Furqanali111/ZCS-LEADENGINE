import pytest
from sqlalchemy import select

from app.models import LeadActivity, Organization, SuppressionEntry
from app.services.suppression import normalize
from tests.test_api import add_lead
from tests.test_search import NPI2, fake, make_job, run


def post(client, kind, value, reason=None):
    return client.post("/api/suppression", json={"kind": kind, "value": value, "reason": reason})


def test_phone_normalizes_formats_to_one_entry(client, db):
    assert post(client, "phone", "(512) 555-0100").status_code == 201
    r = post(client, "phone", "512.555.0100")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_suppressed"
    assert [e.value for e in db.scalars(select(SuppressionEntry))] == ["5125550100"]


def test_npi_must_be_ten_digits(client):
    assert post(client, "npi", "12345").status_code == 422
    with pytest.raises(ValueError):
        normalize("npi", "")
    with pytest.raises(ValueError):
        normalize("phone", "123456")
    with pytest.raises(ValueError):
        normalize("email", "a@b@c")
    assert post(client, "npi", "1234567890").status_code == 201


def test_add_marks_matching_lead_do_not_contact_and_logs_activity(client, db):
    by_npi = add_lead(db, "1000000001", "Alpha")
    by_fax = add_lead(db, "1000000002", "Beta", fax="(512) 555-0199")
    other = add_lead(db, "1000000003", "Gamma", phone="5125550123")
    assert post(client, "npi", "1000000001").status_code == 201
    assert post(client, "phone", "512-555-0199").status_code == 201
    db.expire_all()
    assert by_npi.crm_status == "do_not_contact" and by_fax.crm_status == "do_not_contact"
    assert other.crm_status == "new"
    acts = db.scalars(select(LeadActivity).where(LeadActivity.organization_id == by_npi.id, LeadActivity.type == "status_change")).all()
    assert [(a.from_status, a.to_status) for a in acts] == [("new", "do_not_contact")]


def test_duplicate_is_409(client):
    assert post(client, "npi", "1000000001").status_code == 201
    assert post(client, "npi", "1000000001").status_code == 409


def test_remove_does_not_change_lead_status(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    entry_id = post(client, "npi", "1000000001").json()["id"]
    assert client.delete(f"/api/suppression/{entry_id}").status_code == 204
    assert client.delete(f"/api/suppression/{entry_id}").status_code == 404
    db.expire_all()
    assert org.crm_status == "do_not_contact"
    assert client.get("/api/suppression").json() == []


@pytest.mark.usefixtures("npi_source")
def test_search_save_of_suppressed_npi_is_do_not_contact(db, session_factory):
    npi = str(NPI2[0]["number"])
    db.add(SuppressionEntry(kind="npi", value=npi))
    db.commit()
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fake({"NPI-2": [NPI2]}))
    db.expire_all()
    org = db.scalars(select(Organization).where(Organization.npi == npi)).one()
    assert org.crm_status == "do_not_contact"
    others = db.scalars(select(Organization).where(Organization.npi != npi)).all()
    assert others and all(o.crm_status == "new" for o in others)


@pytest.mark.usefixtures("npi_source")
def test_search_fallback_path_enforces_too(db, session_factory):
    page = [dict(r) for r in NPI2]
    page[0] = {**page[0], "basic": {**page[0]["basic"], "organization_name": "Bad\x00Name"}}
    npi = str(page[1]["number"])
    db.add(SuppressionEntry(kind="npi", value=npi))
    db.commit()
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fake({"NPI-2": [page]}))
    db.expire_all()
    assert db.scalars(select(Organization).where(Organization.npi == npi)).one().crm_status == "do_not_contact"


@pytest.mark.usefixtures("npi_source")
def test_search_rerun_does_not_reset_do_not_contact(db, session_factory):
    fetch = fake({"NPI-2": [NPI2]})
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fetch)
    org = db.scalars(select(Organization)).first()
    db.add(SuppressionEntry(kind="npi", value=org.npi))
    db.commit()
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fetch)
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fetch)
    db.expire_all()
    assert db.get(Organization, org.id).crm_status == "do_not_contact"
    n = db.scalars(select(LeadActivity).where(LeadActivity.organization_id == org.id, LeadActivity.to_status == "do_not_contact")).all()
    assert len(n) == 1  # no-op when already do_not_contact


def test_suppressed_flag_in_lead_out(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    add_lead(db, "1000000002", "Beta")
    db.add(SuppressionEntry(kind="npi", value="1000000001"))
    db.commit()
    flags = {i["npi"]: i["suppressed"] for i in client.get("/api/leads").json()["items"]}
    assert flags == {"1000000001": True, "1000000002": False}
    assert client.get(f"/api/leads/{org.id}").json()["suppressed"] is True


def test_email_entry_is_stored_and_lowercased(client, db):
    r = post(client, "email", "  Boss@Example.COM ")
    assert r.status_code == 201 and r.json()["value"] == "boss@example.com"
    assert post(client, "email", "nope").status_code == 422


def test_phone_plus_one_prefix_matches_ten_digit_storage(client, db):
    assert normalize("phone", "+1 813 671 0064") == normalize("phone", "(813) 671-0064") == "8136710064"
    stored = add_lead(db, "1000000001", "Alpha", phone="8136710064")
    prefixed = add_lead(db, "1000000002", "Beta", fax="+1 (813) 671-0099")
    assert post(client, "phone", "+1 813 671 0064").status_code == 201
    assert post(client, "phone", "+1 813 671 0099").status_code == 201
    db.expire_all()
    assert stored.crm_status == "do_not_contact" and prefixed.crm_status == "do_not_contact"
    r = post(client, "phone", "(813) 671-0064")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_suppressed"


def test_add_entry_integrity_error_is_409(client, db, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    post(client, "npi", "1000000001")
    monkeypatch.setattr(db, "scalar", lambda *a, **k: None)  # the pre-check misses, as in a race
    r = post(client, "npi", "1000000001")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_suppressed"


@pytest.mark.usefixtures("npi_source")
def test_search_save_of_fax_match_is_do_not_contact(db, session_factory):
    fax = "".join(c for c in NPI2[0]["addresses"][0]["fax_number"] if c.isdigit())
    db.add(SuppressionEntry(kind="phone", value=fax))
    db.commit()
    run(session_factory, make_job(db, include_solo=False, include_subparts=True), fake({"NPI-2": [NPI2]}))
    db.expire_all()
    assert db.scalars(select(Organization).where(Organization.npi == str(NPI2[0]["number"]))).one().crm_status == "do_not_contact"


@pytest.mark.usefixtures("npi_source")
def test_enforce_failure_on_fallback_path_is_counted_and_page_continues(db, session_factory, monkeypatch):
    from app.models import SearchJob
    from app.services import search

    page = [dict(r) for r in NPI2]
    page[0] = {**page[0], "basic": {**page[0]["basic"], "organization_name": "Bad\x00Name"}}  # forces the fallback
    calls = []

    def boom(session, ids):
        calls.append(1)
        raise RuntimeError("secret lead data")

    monkeypatch.setattr(search, "enforce", boom)
    job_id = make_job(db, include_solo=False, include_subparts=True)
    run(session_factory, job_id, fake({"NPI-2": [page]}))
    db.expire_all()
    job = db.get(SearchJob, job_id)
    assert job.status == "completed" and calls
    assert job.counters["source_failures"] == 2  # the bad record plus the enforce failure
    assert db.scalars(select(Organization)).all()
