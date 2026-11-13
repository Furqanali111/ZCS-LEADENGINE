import uuid

from app.models import OutreachTemplate


def make(client, **over):
    body = {"name": "Intro", "kind": "email", "subject": "Hello {practice}", "body": "Hi {contact}"} | over
    return client.post("/api/templates", json=body)


def test_create_list_order_update_delete(client):
    r = make(client)
    assert r.status_code == 201
    tid = r.json()["id"]
    assert make(client, name="Script", kind="call", subject=None).status_code == 201
    assert make(client, name="Another").status_code == 201
    assert [(t["kind"], t["name"]) for t in client.get("/api/templates").json()] == [("call", "Script"), ("email", "Another"), ("email", "Intro")]
    r = client.patch(f"/api/templates/{tid}", json={"body": "New body"})
    assert r.status_code == 200 and r.json()["body"] == "New body" and r.json()["subject"] == "Hello {practice}"
    assert client.delete(f"/api/templates/{tid}").status_code == 204
    assert len(client.get("/api/templates").json()) == 2


def test_validation(client):
    assert make(client, name="").status_code == 422
    assert make(client, name="x" * 101).status_code == 422
    assert make(client, body="").status_code == 422
    assert make(client, body="x" * 5001).status_code == 422
    assert make(client, subject="x" * 201).status_code == 422
    assert make(client, kind="sms", subject=None).status_code == 422
    assert make(client, name="Text", kind="message", subject=None).status_code == 201
    r = make(client, kind="call", subject="nope")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_duplicate_name_is_409(client):
    make(client)
    r = make(client)
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_name"
    other = make(client, name="Other").json()["id"]
    r = client.patch(f"/api/templates/{other}", json={"name": "Intro"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_name"


def test_unknown_id_is_404(client):
    missing = uuid.uuid4()
    for r in (client.patch(f"/api/templates/{missing}", json={"body": "x"}), client.delete(f"/api/templates/{missing}")):
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_patch_to_call_clears_subject_and_rejects_subject(client, db):
    tid = make(client).json()["id"]
    r = client.patch(f"/api/templates/{tid}", json={"kind": "call"})
    assert r.status_code == 200 and r.json()["subject"] is None
    assert client.patch(f"/api/templates/{tid}", json={"subject": "x"}).status_code == 422
    assert client.patch(f"/api/templates/{tid}", json={"body": None}).status_code == 422
    assert db.query(OutreachTemplate).count() == 1
