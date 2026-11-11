from datetime import date, datetime, timedelta, timezone

from app.models import LeadActivity, Organization, SearchJob


def org(db, n, status="new", priority=None, state="FL", spec="Family Medicine", follow=None):
    o = Organization(npi=f"{n:010d}", name=f"Org {n}", organization_type="practice", state=state, crm_status=status,
                     priority=priority, primary_taxonomy_desc=spec, next_follow_up_at=follow)
    db.add(o)
    db.flush()
    return o


def act(db, o, type, days_ago, to_status=None):
    db.add(LeadActivity(organization_id=o.id, type=type, summary=None if type == "status_change" else "x",
                        to_status=to_status, occurred_at=datetime.now(timezone.utc) - timedelta(days=days_ago)))


def stats(client, **params):
    return client.get("/api/dashboard/stats", params=params)


def test_dashboard_counts_on_seeded_data(client, db):
    today = date.today()
    org(db, 1, "new", "critical")
    org(db, 2, "new", "high", state="TX", spec="Geriatrics")
    org(db, 3, "meeting_scheduled", "low", follow=today)
    org(db, 4, "converted", None, follow=today - timedelta(days=1))
    org(db, 5, "called", None, follow=today + timedelta(days=1))
    org(db, 6, "do_not_contact", None, follow=today - timedelta(days=3))
    org(db, 7, "not_interested", None, follow=today - timedelta(days=2))  # closed, never due
    db.add(SearchJob(specialty="x", state="FL", target_count=5, sources=["nppes"]))
    db.commit()
    s = stats(client).json()
    assert s["total"] == 7 and s["new_leads"] == 2 and s["critical_high"] == 2
    assert s["follow_ups_due"] == 1 and s["meetings_scheduled"] == 1 and s["converted"] == 1
    assert s["range"] == {"from": str(today - timedelta(days=90)), "to": str(today)}
    assert {"key": "FL", "count": 6} in s["by_state"] and {"key": "TX", "count": 1} in s["by_state"]
    assert {"key": "Geriatrics", "count": 1} in s["by_specialty"]
    assert {"key": "new", "count": 2} in s["by_status"]
    assert len(s["recent_jobs"]) == 1 and s["recent_jobs"][0]["specialty"] == "x"


def test_dashboard_conversion_numerator_denominator_range(client, db):
    a, b, c, d = (org(db, i) for i in range(4))
    act(db, a, "call", 5)
    act(db, a, "email", 4)  # same lead twice counts once
    act(db, b, "meeting", 10)
    act(db, c, "call", 200)  # out of range
    act(db, d, "note", 1)  # not a contact
    act(db, a, "status_change", 2, "converted")
    act(db, a, "status_change", 1, "converted")
    act(db, b, "status_change", 3, "called")  # not converted
    act(db, c, "status_change", 150, "converted")  # out of range
    db.commit()
    conv = stats(client).json()["conversion"]
    assert conv == {"converted": 1, "contacted": 2, "rate": 0.5}
    wide = stats(client, **{"from": str(date.today() - timedelta(days=365))}).json()["conversion"]
    assert wide == {"converted": 2, "contacted": 3, "rate": 2 / 3}


def test_dashboard_range_includes_today_and_excludes_just_before_start(client, db):
    inside, outside = org(db, 1), org(db, 2)
    act(db, inside, "call", 0)
    act(db, outside, "call", 92)  # default range starts 90 days back; 92 stays clear of the UTC/local day edge
    db.commit()
    assert stats(client).json()["conversion"]["contacted"] == 1


def test_dashboard_zero_contacted_rate_is_null(client, db):
    org(db, 1)
    db.commit()
    assert stats(client).json()["conversion"] == {"converted": 0, "contacted": 0, "rate": None}


def test_dashboard_from_after_to_is_422(client):
    r = stats(client, **{"from": "2026-02-02", "to": "2026-02-01"})
    assert r.status_code == 422
    assert set(r.json()["error"]) == {"code", "message"}


def test_dashboard_top_10_limits(client, db):
    states = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI"]
    for i, st in enumerate(states):
        org(db, i, state=st, spec=f"Spec {i:02d}")
    db.commit()
    s = stats(client).json()
    assert len(s["by_state"]) == 10 and len(s["by_specialty"]) == 10
    assert len(s["by_status"]) == 1


def test_dashboard_top_10_ordered_by_count_then_key(client, db):
    counts = {"TX": 3, "FL": 2, "AZ": 2, "HI": 1, "GA": 1, "DE": 1, "CT": 1, "CO": 1, "AR": 1, "AL": 1, "AK": 1}
    n = 0
    for st, c in counts.items():
        for _ in range(c):
            org(db, n, state=st, spec=f"S{n}")
            n += 1
    db.commit()
    by_state = stats(client).json()["by_state"]
    assert [(i["key"], i["count"]) for i in by_state] == [("TX", 3), ("AZ", 2), ("FL", 2)] + [(k, 1) for k in
        ("AK", "AL", "AR", "CO", "CT", "DE", "GA")]
