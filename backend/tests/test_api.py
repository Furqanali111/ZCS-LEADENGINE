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
