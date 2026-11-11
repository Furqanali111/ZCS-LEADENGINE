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
    assert set(r.json()[0]) == {"key", "name", "status", "notes"}


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
    assert (org.fit_score, org.priority) == (85, "critical")

    cfg = load_config()
    cfg["version"] = "2"
    cfg["priority_thresholds"] = {"critical": 90, "high": 80, "medium": 45}
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg))
    assert rescore_all(session_factory, str(p)) == 1
    db.refresh(org)
    assert (org.fit_score, org.priority, org.score.config_version) == (85, "high", "2")
