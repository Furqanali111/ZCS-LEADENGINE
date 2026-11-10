import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Contact, Location, Organization, LeadScore, SourceRecord


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
