import uuid

BODY = {"name": "IM FL", "specialty": "Internal Medicine", "state": "fl", "sources": ["npi_registry"], "target_count": 200}


def make(client, headers=None, **over):
    return client.post("/api/saved-searches", json=BODY | over, headers=headers)


def test_create_list_touch_delete(client):
    r = make(client, headers={"X-Salesperson": "Ali"})
    assert r.status_code == 201
    s = r.json()
    assert s["state"] == "FL" and s["created_by"] == "Ali" and s["last_run_at"] is None and s["enrich"] is False
    assert make(client, name="Second", city=" Miami ").json()["city"] == "Miami"
    assert [x["name"] for x in client.get("/api/saved-searches").json()] == ["Second", "IM FL"]  # newest first
    t = client.post(f"/api/saved-searches/{s['id']}/touch")
    assert t.status_code == 200 and t.json()["last_run_at"] is not None
    assert client.delete(f"/api/saved-searches/{s['id']}").status_code == 204
    assert [x["name"] for x in client.get("/api/saved-searches").json()] == ["Second"]


def test_duplicate_name_ignores_case(client):
    assert make(client).status_code == 201
    r = make(client, name="im fl")
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_name"


def test_validation(client):
    assert make(client, name="").status_code == 422
    assert make(client, name="   ").status_code == 422
    assert make(client, name="x" * 61).status_code == 422
    assert make(client, state="ZZ").status_code == 422
    assert make(client, specialty="").status_code == 422
    assert make(client, target_count=0).status_code == 422
    assert make(client, target_count=50001).status_code == 422
    assert make(client, sources=[]).status_code == 422
    assert make(client, include_practices=False, include_solo=False).status_code == 422


def test_unknown_id_is_404(client):
    missing = uuid.uuid4()
    assert client.delete(f"/api/saved-searches/{missing}").status_code == 404
    assert client.post(f"/api/saved-searches/{missing}/touch").status_code == 404
