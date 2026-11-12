def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_unknown_route_uses_error_shape(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert set(r.json()["error"]) == {"code", "message"}


def test_cors_allows_only_frontend_origin(client):
    r = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_allows_frontend_origin(client):
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_exposes_content_disposition(client):
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert "Content-Disposition" in r.headers["access-control-expose-headers"]


def test_unhandled_error_uses_error_shape(db):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(testing=True)

    @app.get("/boom")
    def boom():
        raise RuntimeError("x")

    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "server_error", "message": "Internal server error"}}


def test_same_database_guard_ignores_driver_and_query():
    from tests.conftest import same_database

    a = "postgresql+psycopg://u:p@h:5432/postgres"
    assert same_database(a, "postgresql://u:p@h/postgres?sslmode=require")
    assert not same_database(a, "postgresql://u:p@h:5432/other")


# ---- sources and search API ----

BODY = {"specialty": "Internal Medicine", "state": "TX", "target_count": 50, "sources": ["npi_registry"]}


def add_source(db, key="npi_registry", name="NPI Registry", status="available"):
    from app.models import SourceConfig

    db.add(SourceConfig(key=key, name=name, status=status))
    db.commit()


def add_job(db, status="queued"):
    from app.models import SearchJob

    job = SearchJob(specialty="x", state="TX", target_count=10, sources=["npi_registry"], status=status)
    db.add(job)
    db.commit()
    return job


def test_sources_list_available_first(client, db):
    add_source(db, "yelp", "Yelp", "not_reviewed")
    add_source(db, "npi_registry", "NPI Registry")
    r = client.get("/api/sources")
    assert r.status_code == 200
    assert [s["key"] for s in r.json()] == ["npi_registry", "yelp"]
    assert set(r.json()[0]) == {"key", "name", "status", "notes", "key_missing"}


def test_sources_flag_missing_brave_key(client, db, monkeypatch):
    from app.config import get_settings

    add_source(db, "brave_search", "Brave Search", "available")
    monkeypatch.setattr(get_settings(), "brave_api_key", None)
    flags = {s["key"]: s["key_missing"] for s in client.get("/api/sources").json()}
    assert flags["brave_search"] is True


def test_create_search_uses_tavily_when_its_key_is_set(client, db, monkeypatch):
    from app.config import get_settings

    add_source(db)
    add_source(db, "tavily_search", "Tavily", "available")
    add_source(db, "practice_websites", "Practice websites", "available")
    monkeypatch.setattr(get_settings(), "tavily_api_key", "t")
    monkeypatch.setattr(get_settings(), "brave_api_key", None)
    r = client.post("/api/search", json={**BODY, "enrich": True})
    assert r.status_code == 201 and r.json()["enrich"] is True


def test_create_search_queues_job(client, db):
    from app.models import SearchJob

    add_source(db)
    r = client.post("/api/search", json=BODY)
    assert r.status_code == 201
    assert r.json()["status"] == "queued"
    assert r.json()["state"] == "TX"
    assert db.get(SearchJob, r.json()["id"]) is not None


def test_create_search_rejects_bad_state(client):
    assert client.post("/api/search", json={**BODY, "state": "ZZ"}).status_code == 422


def test_create_search_rejects_target_over_1200(client):
    assert client.post("/api/search", json={**BODY, "target_count": 1201}).status_code == 422


def test_create_search_requires_a_lead_type(client):
    r = client.post("/api/search", json={**BODY, "include_practices": False, "include_solo": False})
    assert r.status_code == 422


def test_create_search_refuses_unavailable_source(client, db):
    add_source(db, "yelp", "Yelp", "not_reviewed")
    r = client.post("/api/search", json={**BODY, "sources": ["yelp"]})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "source_not_available"


def test_cancel_queued_job(client, db):
    job = add_job(db)
    r = client.post(f"/api/search/{job.id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert r.json()["finished_at"] is not None


def test_cancel_paused_job_is_cancelled(client, db):
    job = add_job(db, status="paused")
    r = client.post(f"/api/search/{job.id}/cancel")
    assert r.json()["status"] == "cancelled" and r.json()["finished_at"] is not None


def test_cancel_running_job_sets_flag_and_terminal_conflicts(client, db):
    running = add_job(db, "running")
    assert client.post(f"/api/search/{running.id}/cancel").json()["status"] == "running"
    db.refresh(running)
    assert running.cancel_requested is True
    done = add_job(db, "completed")
    r = client.post(f"/api/search/{done.id}/cancel")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "invalid_job_state"


def test_resume_only_from_paused_or_failed(client, db):
    done = add_job(db, "completed")
    r = client.post(f"/api/search/{done.id}/resume")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "invalid_job_state"
    paused = add_job(db, "paused")
    paused.error = "boom"
    paused.cancel_requested = True
    db.commit()
    r = client.post(f"/api/search/{paused.id}/resume")
    assert r.json()["status"] == "queued"
    assert r.json()["error"] is None
    db.refresh(paused)
    assert paused.cancel_requested is False


def test_list_searches_newest_first(client, db):
    a, b = add_job(db), add_job(db)
    ids = [j["id"] for j in client.get("/api/search").json()]
    assert ids == [str(b.id), str(a.id)]


def test_get_unknown_job_404(client):
    import uuid

    assert client.get(f"/api/search/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/search/not-a-uuid").status_code == 404


def test_create_search_rejects_non_string_state(client):
    assert client.post("/api/search", json={**BODY, "state": ["TX"]}).status_code == 422
    assert client.post("/api/search", json={**BODY, "state": {}}).status_code == 422


def test_create_search_uppercases_state(client, db):
    add_source(db)
    r = client.post("/api/search", json={**BODY, "state": "tx"})
    assert r.status_code == 201
    assert r.json()["state"] == "TX"


def test_create_search_unknown_or_rejected_source(client, db):
    add_source(db, "bad", "Bad", "rejected")
    for key in ("nope", "bad"):
        r = client.post("/api/search", json={**BODY, "sources": [key]})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "source_not_available"


def test_create_search_field_bounds(client):
    for patch in ({"target_count": 0}, {"specialty": "   "}, {"specialty": "x" * 101}, {"sources": []}):
        assert client.post("/api/search", json={**BODY, **patch}).status_code == 422, patch


def test_create_search_dedupes_sources(client, db):
    add_source(db)
    r = client.post("/api/search", json={**BODY, "sources": ["npi_registry", "npi_registry"]})
    assert r.status_code == 201
    assert r.json()["sources"] == ["npi_registry"]


def test_resume_failed_and_queued(client, db):
    failed = add_job(db, "failed")
    failed.error = "boom"
    db.commit()
    r = client.post(f"/api/search/{failed.id}/resume")
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    assert r.json()["error"] is None
    queued = add_job(db)
    r = client.post(f"/api/search/{queued.id}/resume")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "invalid_job_state"


# ---- leads API ----

def add_lead(db, npi, name, score=None, priority=None, state="TX", city="Austin", crm="new", desc="Internal Medicine", **kw):
    from app.models import Contact, LeadScore, Location, Organization, SourceRecord

    org = Organization(npi=npi, name=name, organization_type="practice", state=state, city=city, crm_status=crm,
                       primary_taxonomy_desc=desc, fit_score=score, priority=priority, **kw)
    db.add(org)
    db.flush()
    if score is not None:
        db.add(LeadScore(organization_id=org.id, components={"specialty": {"points": 25}}, total=score,
                         priority=priority, config_version="1"))
    db.add(Location(organization_id=org.id, purpose="location", address_1="1 Main", zip="78701", is_primary=True))
    db.add(Contact(organization_id=org.id, first_name="Pat", last_name="Lee", role="provider", source_key="npi_registry"))
    db.add(Contact(organization_id=org.id, first_name="Ann", last_name="Boss", title="Admin", role="authorized_official", source_key="npi_registry"))
    db.add(SourceRecord(organization_id=org.id, source_key="npi_registry", external_id=npi, raw={"number": npi}))
    db.commit()
    return org


def seed_leads(db):
    return [
        add_lead(db, "1000000001", "Alpha Clinic", 90, "critical"),
        add_lead(db, "1000000002", "Bravo Care", 70, "high", state="FL", city="Miami"),
        add_lead(db, "1000000003", "Charlie Health", 50, "medium", crm="called"),
        add_lead(db, "1000000004", "Delta 100% Group", 20, "low", state="AZ", city="Phoenix", desc="Cardiology"),
        add_lead(db, "1000000005", "Echo Medical", 85, "critical", dba_name="Echo Docs"),
        add_lead(db, "1000000006", "Foxtrot Unscored"),
    ]


def names(r):
    return [i["name"] for i in r.json()["items"]]


def test_leads_default_sort_is_score_desc(client, db):
    seed_leads(db)
    r = client.get("/api/leads")
    assert names(r) == ["Alpha Clinic", "Echo Medical", "Bravo Care", "Charlie Health", "Delta 100% Group", "Foxtrot Unscored"]
    assert names(client.get("/api/leads?order=asc"))[-1] == "Foxtrot Unscored"
    assert names(client.get("/api/leads?sort=name&order=asc"))[0] == "Alpha Clinic"


def test_leads_filters_combine(client, db):
    seed_leads(db)
    assert names(client.get("/api/leads?state=tx&priority=critical&min_score=88")) == ["Alpha Clinic"]
    assert names(client.get("/api/leads?crm_status=called")) == ["Charlie Health"]
    assert names(client.get("/api/leads?specialty=cardio")) == ["Delta 100% Group"]
    assert client.get("/api/leads?organization_type=solo_provider").json()["total"] == 0


def test_leads_q_matches_name_city_npi(client, db):
    seed_leads(db)
    assert names(client.get("/api/leads?q=bravo")) == ["Bravo Care"]
    assert names(client.get("/api/leads?q=phoenix")) == ["Delta 100% Group"]
    assert names(client.get("/api/leads?q=1000000003")) == ["Charlie Health"]
    assert names(client.get("/api/leads?q=echo docs")) == ["Echo Medical"]
    assert names(client.get("/api/leads?q=%25")) == ["Delta 100% Group"]
    assert client.get("/api/leads?q=_").json()["total"] == 0


def _follow_ups(db):
    from datetime import date, timedelta

    t = date.today()
    return [
        add_lead(db, "2000000001", "Past Co", next_follow_up_at=t - timedelta(days=2)),
        add_lead(db, "2000000002", "Today Co", next_follow_up_at=t),
        add_lead(db, "2000000003", "Future Co", next_follow_up_at=t + timedelta(days=3)),
        add_lead(db, "2000000004", "Never Co"),
        add_lead(db, "2000000005", "Closed Co", crm="converted", next_follow_up_at=t - timedelta(days=5)),
    ]


def test_follow_up_due_overdue_none_filters(client, db):
    _follow_ups(db)
    assert sorted(names(client.get("/api/leads?follow_up=due"))) == ["Past Co", "Today Co"]
    assert names(client.get("/api/leads?follow_up=overdue")) == ["Past Co"]
    assert sorted(names(client.get("/api/leads?follow_up=none"))) == ["Never Co"]
    assert client.get("/api/leads?follow_up=bogus").status_code == 422


def test_closed_statuses_never_due(client, db):
    _follow_ups(db)
    for f in ("due", "overdue"):
        assert "Closed Co" not in names(client.get(f"/api/leads?follow_up={f}"))


def test_sort_by_follow_up_nulls_last(client, db):
    _follow_ups(db)
    got = names(client.get("/api/leads?sort=follow_up&order=asc"))
    assert got[:3] == ["Closed Co", "Past Co", "Today Co"] and got[3] == "Future Co"
    assert set(got[4:]) == {"Never Co"}
    # default order for this sort is still honoured when asked desc: nulls stay last
    assert names(client.get("/api/leads?sort=follow_up&order=desc"))[-1] == "Never Co"


def test_q_matches_contact_name(client, db):
    seed_leads(db)
    assert client.get("/api/leads?q=boss").json()["total"] == 6
    assert client.get("/api/leads?q=pat lee").json()["total"] == 6  # full name matches too
    assert client.get("/api/leads?q=zzz").json()["total"] == 0
    assert client.get("/api/leads?q=_").json()["total"] == 0


def test_leads_filter_by_search_job(client, db):
    from app.models import SearchJobLead

    orgs = seed_leads(db)
    job = add_job(db)
    db.add(SearchJobLead(search_job_id=job.id, organization_id=orgs[1].id, was_new=True))
    db.commit()
    assert names(client.get(f"/api/leads?search_job_id={job.id}")) == ["Bravo Care"]


def test_leads_pagination_total(client, db):
    seed_leads(db)
    j = client.get("/api/leads?page_size=2&page=3").json()
    assert (len(j["items"]), j["total"], j["page"], j["page_size"]) == (2, 6, 3, 2)
    assert client.get("/api/leads?page_size=201").status_code == 422
    assert client.get("/api/leads?page=0").status_code == 422


def test_lead_includes_contact_score_source(client, db):
    seed_leads(db)
    lead = client.get("/api/leads?q=alpha").json()["items"][0]
    assert lead["contact"]["role"] == "authorized_official" and lead["contact"]["last_name"] == "Boss"
    assert lead["score"]["config_version"] == "1" and "specialty" in lead["score"]["components"]
    assert lead["source"]["source_key"] == "npi_registry" and lead["source"]["collected_at"]
    assert lead["locations"][0]["is_primary"] is True
    unscored = client.get("/api/leads?q=foxtrot").json()["items"][0]
    assert unscored["score"] is None and unscored["fit_score"] is None


def test_patch_status_persists(client, db):
    org = seed_leads(db)[0]
    r = client.patch(f"/api/leads/{org.id}", json={"crm_status": "called"})
    assert r.status_code == 200 and r.json()["crm_status"] == "called"
    db.refresh(org)
    assert org.crm_status == "called" and org.status_updated_at is not None


def test_patch_invalid_status_422(client, db):
    org = seed_leads(db)[0]
    assert client.patch(f"/api/leads/{org.id}", json={"crm_status": "won"}).status_code == 422


def test_patch_rejects_other_fields(client, db):
    org = seed_leads(db)[0]
    assert client.patch(f"/api/leads/{org.id}", json={"name": "x"}).status_code == 422
    assert client.patch(f"/api/leads/{org.id}", json={"crm_status": "called", "name": "x"}).status_code == 422


def test_patch_unknown_id_404(client):
    import uuid

    for lead_id in (uuid.uuid4(), "not-a-uuid"):
        r = client.patch(f"/api/leads/{lead_id}", json={"crm_status": "called"})
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_leads_invalid_filters_422(client):
    for qs in ("state=ZZ", "priority=urgent", "min_score=101", "min_score=-1", "organization_type=x",
               "crm_status=won", "sort=bogus", "search_job_id=nope"):
        assert client.get(f"/api/leads?{qs}").status_code == 422, qs


def test_rescore_updates_all(db, session_factory, tmp_path):
    import json

    from app.models import Organization, SourceRecord
    from app.rescore import rescore_all
    from app.services.scoring import load_config

    raw = {"number": "1111111111", "enumeration_type": "NPI-2",
           "basic": {"organization_name": "Core Practice", "authorized_official_first_name": "A",
                     "authorized_official_last_name": "B", "authorized_official_title_or_position": "Owner"},
           "taxonomies": [{"code": "207Q00000X", "desc": "Family Medicine", "primary": True}],
           "addresses": [{"address_purpose": "LOCATION", "city": "Austin", "state": "TX", "telephone_number": "512-555-0100"}]}
    org = Organization(npi="1111111111", name="Core Practice", organization_type="practice", state="TX")
    db.add(org)
    db.flush()
    db.add(SourceRecord(organization_id=org.id, source_key="npi_registry", external_id="1111111111", raw=raw))
    db.add(Organization(npi="2222222222", name="No Source", organization_type="practice", state="TX"))
    db.commit()

    assert rescore_all(session_factory) == 1
    db.refresh(org)
    assert (org.fit_score, org.priority) == (85, "medium")

    cfg = load_config()
    cfg["version"] = "2"
    cfg["priority_thresholds"] = {"critical": 90, "high": 80, "medium": 45}
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg))
    assert rescore_all(session_factory, str(p)) == 1
    db.refresh(org)
    assert (org.fit_score, org.priority, org.score.config_version) == (85, "high", "2")


def test_patch_suppressed_lead_cannot_leave_do_not_contact(client, db):
    org = add_lead(db, "1000000009", "Sup Co")
    client.post("/api/suppression", json={"kind": "npi", "value": "1000000009"})
    r = client.patch(f"/api/leads/{org.id}", json={"crm_status": "new"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "lead_suppressed"
    assert client.get(f"/api/leads/{org.id}").json()["crm_status"] == "do_not_contact"
    assert client.patch(f"/api/leads/{org.id}", json={"next_follow_up_at": "2026-12-01"}).status_code == 200
    assert client.patch(f"/api/leads/{org.id}", json={"crm_status": "do_not_contact"}).status_code == 200


def test_rescore_passes_staff_with_title(db, session_factory):
    from app.models import Contact, Organization, SourceRecord
    from app.rescore import rescore_all

    raw = {"number": "3333333333", "enumeration_type": "NPI-2", "basic": {"organization_name": "Staff Co"},
           "taxonomies": [{"code": "207Q00000X", "desc": "Family Medicine", "primary": True}],
           "addresses": [{"address_purpose": "LOCATION", "city": "Austin", "state": "TX"}]}
    org = Organization(npi="3333333333", name="Staff Co", organization_type="practice", state="TX")
    db.add(org)
    db.flush()
    db.add(SourceRecord(organization_id=org.id, source_key="npi_registry", external_id="3333333333", raw=raw))
    db.add(Contact(organization_id=org.id, first_name="Ann", last_name="Lee", title="Practice Manager",
                   role="staff", source_key="website"))
    db.commit()
    rescore_all(session_factory)
    db.refresh(org)
    assert org.score.components["decision_maker"]["points"] == 10

def test_reject_website_is_idempotent(client, db):
    from app.models import LeadActivity

    org = add_lead(db, "1000000009", "Acme", website="https://acme.example", enrichment_status="enriched")
    first = client.patch(f"/api/leads/{org.id}", json={"reject_website": True}).json()
    again = client.patch(f"/api/leads/{org.id}", json={"reject_website": True})
    assert again.status_code == 200 and again.json() == first
    db.expire_all()
    assert db.query(LeadActivity).filter_by(organization_id=org.id, summary="Website rejected").count() == 1


def test_reject_website_rescores_without_website_staff(client, db):
    from app.models import Contact, SourceRecord
    from app.services.leads import rescore_org

    raw = {"number": "3333333333", "enumeration_type": "NPI-2", "basic": {"organization_name": "Staff Co"},
           "taxonomies": [{"code": "207Q00000X", "desc": "Family Medicine", "primary": True}],
           "addresses": [{"address_purpose": "LOCATION", "city": "Austin", "state": "TX"}]}
    org = add_lead(db, "3333333333", "Staff Co", website="https://staff.example", enrichment_status="enriched")
    db.query(SourceRecord).filter_by(organization_id=org.id).update({"raw": raw})
    db.add(Contact(organization_id=org.id, first_name="Ann", last_name="Lee", title="practice manager",
                   role="staff", source_key="practice_website"))
    db.commit()
    rescore_org(db, org)
    db.commit()
    assert org.score.components["decision_maker"]["points"] == 10
    assert client.patch(f"/api/leads/{org.id}", json={"reject_website": True}).status_code == 200
    db.expire_all()
    assert org.score.components["decision_maker"]["points"] == 0 and org.fit_score == org.score.total


# ---- website and emails ----

def add_web_contacts(db, org):
    from datetime import datetime, timezone

    from app.models import Contact

    t = datetime(2026, 11, 12, tzinfo=timezone.utc)
    db.add(Contact(organization_id=org.id, first_name="Jane", last_name="Doe", title="Practice Manager", role="staff",
                   source_key="practice_website", email="jane@acme.example", email_status="found_on_page",
                   source_url="https://acme.example/team", collected_at=t))
    db.add(Contact(organization_id=org.id, first_name="", last_name="", role="general", source_key="practice_website",
                   email="info@acme.example", email_status="found_on_page",
                   source_url="https://acme.example/contact", collected_at=t))
    db.commit()


def test_detail_exposes_website_evidence_and_contacts(client, db):
    org = add_lead(db, "1000000009", "Acme", website="https://acme.example", enrichment_status="enriched",
                   website_evidence={"matched": ["phone"]})
    add_web_contacts(db, org)
    lead = client.get(f"/api/leads/{org.id}").json()
    assert lead["website"] == "https://acme.example" and lead["enrichment_status"] == "enriched"
    assert lead["website_evidence"] == {"matched": ["phone"]}
    assert len(lead["contacts"]) == 4
    jane = next(c for c in lead["contacts"] if c["email"] == "jane@acme.example")
    assert jane["source_url"] == "https://acme.example/team" and jane["email_status"] == "found_on_page"
    assert jane["collected_at"]
    assert lead["primary_email"] == "info@acme.example"  # first general contact wins over staff


def test_primary_email_falls_back_to_staff_then_null(client, db):
    from app.models import Contact

    org = add_lead(db, "1000000009", "Acme")
    assert client.get(f"/api/leads/{org.id}").json()["primary_email"] is None
    db.add(Contact(organization_id=org.id, first_name="Jane", last_name="Doe", role="staff", source_key="practice_website",
                   email="jane@acme.example"))
    db.commit()
    db.expire_all()  # the test and the app share one session
    assert client.get("/api/leads?q=acme").json()["items"][0]["primary_email"] == "jane@acme.example"


def test_reject_website(client, db):
    from app.models import Contact, LeadActivity

    org = add_lead(db, "1000000009", "Acme", website="https://acme.example", enrichment_status="enriched",
                   website_evidence={"matched": ["phone"]})
    add_web_contacts(db, org)
    r = client.patch(f"/api/leads/{org.id}", json={"reject_website": True})
    assert r.status_code == 200
    body = r.json()
    assert body["website"] is None and body["website_evidence"] is None
    assert body["enrichment_status"] == "rejected_by_user" and body["primary_email"] is None
    assert len(body["contacts"]) == 2  # NPI contacts survive
    db.expire_all()
    assert {c.source_key for c in db.query(Contact).filter_by(organization_id=org.id)} == {"npi_registry"}
    assert db.query(LeadActivity).filter_by(organization_id=org.id, type="note", summary="Website rejected").count() == 1


def test_reject_website_false_or_alone_validates(client, db):
    org = add_lead(db, "1000000009", "Acme")
    assert client.patch(f"/api/leads/{org.id}", json={"reject_website": False}).status_code == 422
    assert client.patch(f"/api/leads/{org.id}", json={"reject_website": None}).status_code == 422
    assert client.patch(f"/api/leads/{org.id}", json={}).status_code == 422
    r = client.patch(f"/api/leads/{org.id}", json={"reject_website": True, "crm_status": "called"})
    assert r.status_code == 200 and r.json()["crm_status"] == "called"


def test_has_website_and_has_email_filters(client, db):
    from app.models import Contact

    a = add_lead(db, "1000000001", "Alpha", website="https://a.example")
    b = add_lead(db, "1000000002", "Bravo")
    db.add(Contact(organization_id=b.id, role="general", source_key="practice_website", email="x@b.example"))
    db.commit()
    assert names(client.get("/api/leads?has_website=true")) == ["Alpha"]
    assert names(client.get("/api/leads?has_email=true")) == ["Bravo"]


def test_create_search_enrich_needs_sources_and_key(client, db, monkeypatch):
    from app.config import get_settings

    add_source(db)
    body = {**BODY, "enrich": True}
    monkeypatch.setattr(get_settings(), "brave_api_key", "k")
    r = client.post("/api/search", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "source_not_available"
    add_source(db, "brave_search", "Brave")
    add_source(db, "practice_websites", "Sites", "not_reviewed")
    assert client.post("/api/search", json=body).status_code == 422
    db.execute(__import__("sqlalchemy").text("UPDATE source_configs SET status='available' WHERE key='practice_websites'"))
    db.commit()
    monkeypatch.setattr(get_settings(), "brave_api_key", None)
    r = client.post("/api/search", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "missing_api_key"
    monkeypatch.setattr(get_settings(), "brave_api_key", "k")
    r = client.post("/api/search", json=body)
    assert r.status_code == 201 and r.json()["enrich"] is True
    assert client.post("/api/search", json=BODY).json()["enrich"] is False


def test_search_progress_read_and_reset(client, db):
    from app.models import SearchProgress

    q = "specialty=Internal%20Medicine&state=tx"
    assert client.get(f"/api/search/progress?{q}").json() == {"leads_fetched": 0, "exhausted": False}
    db.add(SearchProgress(specialty="internal medicine", state="TX", city="", include_subparts=True, include_hospitals=False,
                          cursor={"practices": {"slices": [], "skip": 0}}, leads_fetched=600))
    db.commit()
    assert client.get(f"/api/search/progress?{q}").json() == {"leads_fetched": 600, "exhausted": True}
    assert client.get(f"/api/search/progress?{q}&include_hospitals=true").json()["leads_fetched"] == 0  # separate filters, separate cursor
    assert client.delete(f"/api/search/progress?{q}").status_code == 204
    assert client.get(f"/api/search/progress?{q}").json()["leads_fetched"] == 0


def test_create_search_accepts_more_than_1200(client, db):
    add_source(db)
    r = client.post("/api/search", json={**BODY, "target_count": 5000})
    assert r.status_code == 201 and r.json()["target_count"] == 5000
    assert client.post("/api/search", json={**BODY, "target_count": 50001}).status_code == 422


def test_leads_sort_by_email_and_website(client, db):
    from datetime import datetime, timezone
    from app.models import Contact, Organization
    for npi, name, site, email in (("1", "A", "b.com", "z@x.com"), ("2", "B", "a.com", "a@x.com"), ("3", "C", None, None)):
        o = Organization(npi=npi, name=name, organization_type="practice", state="TX", website=site)
        db.add(o)
        db.flush()
        if email:
            db.add(Contact(organization_id=o.id, role="general", email=email, source_key="practice_websites", source_url="https://x.com", collected_at=datetime.now(timezone.utc)))
    db.commit()
    names = lambda q: [i["name"] for i in client.get(f"/api/leads?{q}").json()["items"]]
    assert names("sort=email&order=asc") == ["B", "A", "C"]
    assert names("sort=website&order=desc") == ["A", "B", "C"]
