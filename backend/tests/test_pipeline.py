from app.constants import CRM_STATUSES
from app.models import Organization


def org(db, n, status="new", score=None, name=None):
    o = Organization(npi=f"{n:010d}", name=name or f"Org {n:03d}", organization_type="practice", state="FL", city="Tampa",
                     crm_status=status, fit_score=score)
    db.add(o)
    return o


def test_pipeline_returns_all_columns_with_counts(client, db):
    for i in range(3):
        org(db, i)
    org(db, 10, "called")
    db.commit()
    cols = client.get("/api/pipeline").json()["columns"]
    assert [c["status"] for c in cols] == list(CRM_STATUSES)
    counts = {c["status"]: c["count"] for c in cols}
    assert counts["new"] == 3 and counts["called"] == 1 and counts["converted"] == 0
    assert all(set(c["leads"][0]) == {"id", "name", "city", "state", "organization_type", "fit_score", "priority", "owner",
                                      "next_follow_up_at", "last_contacted_at"} for c in cols if c["leads"])


def test_pipeline_cards_ordered_by_score(client, db):
    org(db, 1, score=40, name="B")
    org(db, 2, score=90, name="C")
    org(db, 3, score=None, name="A")
    org(db, 4, score=40, name="A2")
    db.commit()
    new = client.get("/api/pipeline").json()["columns"][0]
    assert [c["name"] for c in new["leads"]] == ["C", "A2", "B", "A"]


def test_pipeline_load_more_and_past_end_is_empty(client, db):
    for i in range(5):
        org(db, i, score=i)
    db.commit()
    board = client.get("/api/pipeline?limit=2").json()["columns"][0]
    assert board["count"] == 5 and len(board["leads"]) == 2
    page = client.get("/api/pipeline/new?offset=2&limit=2").json()
    assert page["status"] == "new" and page["count"] == 5
    assert [c["fit_score"] for c in page["leads"]] == [2, 1]
    end = client.get("/api/pipeline/new?offset=50")
    assert end.status_code == 200 and end.json()["leads"] == [] and end.json()["count"] == 5


def test_unknown_status_is_422(client):
    r = client.get("/api/pipeline/bogus")
    assert r.status_code == 422
    assert set(r.json()["error"]) == {"code", "message"}


def test_pipeline_same_score_same_name_ties_break_by_id(client, db):
    ids = [org(db, i, score=50, name="Same") for i in range(5)]
    db.commit()
    expected = [str(i) for i in sorted(o.id for o in ids)]
    new = client.get("/api/pipeline").json()["columns"][0]
    assert [c["id"] for c in new["leads"]] == expected
    assert [c["id"] for c in client.get("/api/pipeline/new").json()["leads"]] == expected
