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
