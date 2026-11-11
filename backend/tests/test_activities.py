import uuid
from datetime import datetime, timedelta, timezone

from app.models import LeadActivity
from app.services.activities import add_activity, change_status
from tests.test_api import add_lead

T0 = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)


def acts(db, org):
    return db.query(LeadActivity).filter_by(organization_id=org.id).all()


def test_call_sets_last_contacted(db):
    org = add_lead(db, "1000000001", "Alpha")
    for t in ("call", "email", "meeting"):
        org.last_contacted_at = None
        add_activity(db, org, type=t, occurred_at=T0, summary="x")
        assert org.last_contacted_at == T0


def test_note_does_not_set_last_contacted(db):
    org = add_lead(db, "1000000001", "Alpha")
    add_activity(db, org, type="note", occurred_at=T0, summary="x")
    add_activity(db, org, type="outcome", occurred_at=T0, summary="x", outcome="spoke")
    assert org.last_contacted_at is None


def test_older_call_does_not_move_last_contacted_back(db):
    org = add_lead(db, "1000000001", "Alpha")
    add_activity(db, org, type="call", occurred_at=T0, summary="x")
    add_activity(db, org, type="call", occurred_at=T0 - timedelta(days=3), summary="old")
    assert org.last_contacted_at == T0


def test_status_change_writes_one_activity_with_from_and_to(db):
    org = add_lead(db, "1000000001", "Alpha")
    assert change_status(db, org, "called") is True
    db.commit()
    (a,) = acts(db, org)
    assert (a.type, a.from_status, a.to_status, a.summary) == ("status_change", "new", "called", None)
    assert org.crm_status == "called" and org.status_updated_at is not None


def test_same_status_writes_nothing(db):
    org = add_lead(db, "1000000001", "Alpha")
    assert change_status(db, org, "new") is False
    db.commit()
    assert acts(db, org) == [] and org.status_updated_at is None


def test_activity_summary_limit_2000(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    url = f"/api/leads/{org.id}/activities"
    assert client.post(url, json={"type": "note", "summary": "x" * 2000}).status_code == 201
    assert client.post(url, json={"type": "note", "summary": "x" * 2001}).status_code == 422
    assert client.post(url, json={"type": "note"}).status_code == 422
    assert client.post(url, json={"type": "bogus", "summary": "x"}).status_code == 422
    assert client.post(url, json={"type": "status_change", "summary": "x"}).status_code == 422
    assert client.post(url, json={"type": "call", "summary": "x", "outcome": "won"}).status_code == 422


def test_post_activity_with_follow_up_updates_snapshot(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    r = client.post(f"/api/leads/{org.id}/activities",
                    json={"type": "call", "summary": "left voicemail", "outcome": "no_answer",
                          "occurred_at": T0.isoformat(), "next_follow_up_at": "2026-11-15"})
    assert r.status_code == 201 and r.json()["type"] == "call" and r.json()["outcome"] == "no_answer"
    detail = client.get(f"/api/leads/{org.id}").json()
    assert detail["next_follow_up_at"] == "2026-11-15"
    assert datetime.fromisoformat(detail["last_contacted_at"]) == T0


def test_post_activity_naive_datetime_is_treated_as_utc(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    url = f"/api/leads/{org.id}/activities"
    assert client.post(url, json={"type": "call", "summary": "a", "occurred_at": "2026-11-01T12:00:00"}).status_code == 201
    assert client.post(url, json={"type": "call", "summary": "b", "occurred_at": "2026-11-02T12:00:00+00:00"}).status_code == 201


def test_patch_null_follow_up_clears_it(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    assert client.patch(f"/api/leads/{org.id}", json={"next_follow_up_at": "2026-12-01"}).json()["next_follow_up_at"] == "2026-12-01"
    r = client.patch(f"/api/leads/{org.id}", json={"next_follow_up_at": None})
    assert r.status_code == 200 and r.json()["next_follow_up_at"] is None
    assert acts(db, org) == []


def test_patch_status_and_follow_up_together(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    r = client.patch(f"/api/leads/{org.id}", json={"crm_status": "called", "next_follow_up_at": "2026-12-01"})
    assert r.status_code == 200 and r.json()["crm_status"] == "called"
    assert len(acts(db, org)) == 1
    client.patch(f"/api/leads/{org.id}", json={"crm_status": "called"})
    assert len(acts(db, org)) == 1


def test_patch_empty_body_is_422(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    for body in ({}, {"name": "x"}, {"crm_status": None}):
        assert client.patch(f"/api/leads/{org.id}", json=body).status_code == 422, body


def test_get_lead_detail_and_404(client, db):
    org = add_lead(db, "1000000001", "Alpha", 90, "critical")
    r = client.get(f"/api/leads/{org.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Alpha" and body["score"]["components"] and body["locations"] and body["contact"]
    assert body["suppressed"] is False and body["last_contacted_at"] is None
    for lead_id in (uuid.uuid4(), "not-a-uuid"):
        r = client.get(f"/api/leads/{lead_id}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.get(f"/api/leads/{uuid.uuid4()}/activities").status_code == 404
    assert client.post(f"/api/leads/{uuid.uuid4()}/activities", json={"type": "note", "summary": "x"}).status_code == 404


def test_activities_listed_newest_first_and_paginated(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    for i in range(5):
        add_activity(db, org, type="note", occurred_at=T0 + timedelta(days=i), summary=f"n{i}")
    db.commit()
    body = client.get(f"/api/leads/{org.id}/activities?page_size=2").json()
    assert [a["summary"] for a in body["items"]] == ["n4", "n3"]
    assert (body["total"], body["page"], body["page_size"]) == (5, 1, 2)
    assert [a["summary"] for a in client.get(f"/api/leads/{org.id}/activities?page=3&page_size=2").json()["items"]] == ["n0"]
    assert client.get(f"/api/leads/{org.id}/activities?page=0").status_code == 422


def test_no_put_or_delete_routes_for_activities(client, db):
    org = add_lead(db, "1000000001", "Alpha")
    add_activity(db, org, type="note", summary="x")
    db.commit()
    aid = acts(db, org)[0].id
    for url in (f"/api/leads/{org.id}/activities/{aid}", f"/api/leads/{org.id}/activities"):
        for method in ("put", "patch", "delete"):
            assert getattr(client, method)(url).status_code in (404, 405), (method, url)
