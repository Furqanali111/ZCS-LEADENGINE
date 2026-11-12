from app.models import LeadActivity, Organization


def make(db, npi="1", status="new"):
    o = Organization(npi=npi, name=f"Org {npi}", organization_type="practice", state="TX", crm_status=status)
    db.add(o)
    db.commit()
    return str(o.id)


def as_(name):
    return {"X-Salesperson": name}


def test_claim_sets_owner_and_in_progress(client, db):
    lid = make(db)
    r = client.post(f"/api/leads/{lid}/claim", headers=as_("Ali"))
    assert r.status_code == 200 and r.json()["owner"] == "Ali" and r.json()["crm_status"] == "in_progress"
    acts = client.get(f"/api/leads/{lid}/activities").json()["items"]
    assert acts[0]["type"] == "status_change" and acts[0]["actor"] == "Ali"


def test_second_person_cannot_claim_but_same_person_can_repeat(client, db):
    lid = make(db)
    client.post(f"/api/leads/{lid}/claim", headers=as_("Ali"))
    other = client.post(f"/api/leads/{lid}/claim", headers=as_("Sara"))
    assert other.status_code == 409 and other.json()["error"]["code"] == "already_claimed" and "Ali" in other.json()["error"]["message"]
    assert client.post(f"/api/leads/{lid}/claim", headers=as_("ali")).status_code == 200  # same name, any case


def test_claim_needs_a_name(client, db):
    assert client.post(f"/api/leads/{make(db)}/claim").status_code == 400


def test_choosing_in_progress_in_the_dropdown_claims(client, db):
    lid = make(db)
    assert client.patch(f"/api/leads/{lid}", json={"crm_status": "in_progress"}, headers=as_("Ali")).json()["owner"] == "Ali"
    assert client.patch(f"/api/leads/{lid}", json={"crm_status": "in_progress"}, headers=as_("Sara")).status_code == 409


def test_release_clears_owner_and_resets_status(client, db):
    lid = make(db)
    client.post(f"/api/leads/{lid}/claim", headers=as_("Ali"))
    j = client.post(f"/api/leads/{lid}/release", headers=as_("Ali")).json()
    assert j["owner"] is None and j["crm_status"] == "new"


def test_owner_filter_and_owner_list(client, db):
    a, b = make(db, "1"), make(db, "2")
    make(db, "3")
    client.post(f"/api/leads/{a}/claim", headers=as_("Ali"))
    client.post(f"/api/leads/{b}/claim", headers=as_("Sara"))
    names = lambda q: sorted(i["name"] for i in client.get(f"/api/leads?{q}").json()["items"])
    assert names("owner=Ali") == ["Org 1"] and names("owner=none") == ["Org 3"]
    assert client.get("/api/owners").json() == ["Ali", "Sara"]


def test_activities_record_who_logged_them(client, db):
    lid = make(db)
    client.post(f"/api/leads/{lid}/activities", json={"type": "call", "summary": "hi", "outcome": "spoke"}, headers=as_("Ali"))
    assert db.query(LeadActivity).one().actor == "Ali"


def test_claim_refused_for_suppressed_or_closed_leads(client, db):
    from app.models import SuppressionEntry
    a, b = make(db, "1"), make(db, "2", status="converted")
    db.add(SuppressionEntry(kind="npi", value="1", reason="test"))
    db.commit()
    assert client.post(f"/api/leads/{a}/claim", headers=as_("Ali")).json()["error"]["code"] == "lead_suppressed"
    assert client.post(f"/api/leads/{b}/claim", headers=as_("Ali")).json()["error"]["code"] == "lead_closed"
    assert client.patch(f"/api/leads/{a}", json={"crm_status": "in_progress"}, headers=as_("Ali")).status_code == 409


def test_reclaim_keeps_the_original_spelling_and_filter_ignores_case(client, db):
    lid = make(db)
    client.post(f"/api/leads/{lid}/claim", headers=as_("Ali"))
    assert client.post(f"/api/leads/{lid}/claim", headers=as_("ali")).json()["owner"] == "Ali"
    assert len(client.get("/api/leads?owner=ALI").json()["items"]) == 1
    assert client.get("/api/owners").json() == ["Ali"]


def test_bad_header_values_are_cleaned_not_500(client, db):
    lid = make(db)
    r = client.post(f"/api/leads/{lid}/claim", headers={"X-Salesperson": "A%00l%0Ai" + "x" * 80})
    assert r.status_code == 200 and r.json()["owner"] == ("Ali" + "x" * 80)[:40]
    other = make(db, "2")
    assert client.post(f"/api/leads/{other}/claim", headers=as_("none")).status_code == 400  # reserved word


def test_only_the_owner_can_release(client, db):
    lid = make(db)
    client.post(f"/api/leads/{lid}/claim", headers=as_("Ali"))
    assert client.post(f"/api/leads/{lid}/release", headers=as_("Sara")).status_code == 409
    assert client.post(f"/api/leads/{lid}/release").status_code == 400
    assert client.get(f"/api/leads/{lid}").json()["owner"] == "Ali"
    notes = [a["summary"] for a in client.post(f"/api/leads/{lid}/release", headers=as_("ali")).json() and client.get(f"/api/leads/{lid}/activities").json()["items"]]
    assert "Released by Ali" in notes

