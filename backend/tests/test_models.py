import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import Contact, LeadActivity, LeadScore, Location, Organization, SourceRecord, SuppressionEntry


def org(**kw):
    return Organization(**{"npi": "1", "name": "Acme Clinic", "organization_type": "practice", "state": "TX", **kw})


def test_duplicate_npi_rejected(db):
    db.add(org())
    db.commit()
    db.add(org())
    with pytest.raises(IntegrityError):
        db.commit()


def test_invalid_state_rejected(db):
    db.add(org(state="ZZ"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_invalid_crm_status_rejected(db):
    db.add(org(crm_status="maybe"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_new_org_defaults(db):
    o = org()
    db.add(o)
    db.commit()
    assert o.crm_status == "new"
    assert o.fit_score is None
    assert o.id is not None and o.created_at is not None


def test_deleting_org_removes_children(db):
    o = org()
    o.locations.append(Location(purpose="location", address_1="1 Main", city="Austin", state="TX", zip="78701", is_primary=True))
    o.contacts.append(Contact(first_name="A", last_name="B", role="authorized_official", source_key="npi_registry"))
    o.score = LeadScore(components={}, total=50, priority="medium", config_version="1")
    o.source_records.append(SourceRecord(source_key="npi_registry", external_id="1", raw={}))
    db.add(o)
    db.commit()
    db.delete(o)
    db.commit()
    for m in (Location, Contact, LeadScore, SourceRecord):
        assert db.scalars(select(m)).all() == []


def test_location_without_address_defaults_to_empty_and_stays_unique(db):
    o = org()
    o.locations.append(Location(purpose="location"))
    db.add(o)
    db.commit()
    loc = o.locations[0]
    assert (loc.address_1, loc.zip) == ("", "")
    o.locations.append(Location(purpose="location"))
    with pytest.raises(IntegrityError):
        db.commit()


def activity(o, **kw):
    return LeadActivity(**{"organization_id": o.id, "type": "note", "summary": "hello", **kw})


def saved_org(db, **kw):
    o = org(**kw)
    db.add(o)
    db.commit()
    return o


def test_activity_update_is_rejected(db):
    o = saved_org(db)
    a = activity(o)
    db.add(a)
    db.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE lead_activities SET summary = 'x'"))
    db.rollback()


def test_activity_delete_is_rejected(db):
    o = saved_org(db)
    db.add(activity(o))
    db.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM lead_activities"))
    db.rollback()


@pytest.mark.parametrize("kw", [
    {"type": "email_blast"},
    {"outcome": "won"},
    {"summary": "x" * 2001},
    {"summary": None},
])
def test_activity_type_and_outcome_checks(db, kw):
    o = saved_org(db)
    db.add(activity(o, **kw))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_status_change_needs_no_summary(db):
    o = saved_org(db)
    db.add(activity(o, type="status_change", summary=None, from_status="new", to_status="called"))
    db.commit()


def test_suppression_unique_per_kind_value(db):
    db.add(SuppressionEntry(kind="npi", value="123"))
    db.add(SuppressionEntry(kind="phone", value="123"))
    db.commit()
    db.add(SuppressionEntry(kind="npi", value="123"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(SuppressionEntry(kind="fax", value="1"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_suppression_survives_organization_delete(db):
    o = saved_org(db)
    db.add(SuppressionEntry(kind="npi", value=o.npi))
    db.commit()
    db.delete(o)
    db.commit()
    assert db.scalars(select(SuppressionEntry)).one().value == "1"


def test_organization_with_activities_cannot_be_deleted(db):
    o = saved_org(db)
    db.add(activity(o))
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM organizations"))
    db.rollback()
