import pytest
from sqlalchemy import select

from app.api.leads import maps_lookup
from app.enrich_maps import run
from app.models import Location, Organization, OrganizationPhone, SourceConfig
from app.services.maps import enrich_maps, maps_url, matches, street_tokens
from app.sources.gmaps import Listing, MapsBlocked, clean_phone, parse_hours

ADDRESS = "2500 Harbor Blvd, Port Charlotte, FL 33952, United States"
HOURS = [{"day": "Monday", "hours": "Open 24 hours"}]


def hospital(db, npi="1", phone="941-766-4122", type_="hospital", address="2500 HARBOR BLVD"):
    o = Organization(npi=npi, name="ADVENTHEALTH PORT CHARLOTTE INC", organization_type=type_, state="FL", city="PORT CHARLOTTE", phone=phone)
    db.add(o)
    db.flush()
    db.add(Location(organization_id=o.id, purpose="location", address_1=address, city="PORT CHARLOTTE", state="FL", zip="339524321"))
    db.commit()
    return o


def listing(**kw):
    return Listing(**{"name": "AdventHealth Port Charlotte", "address": ADDRESS, "phone": "941-766-4122", "hours": HOURS,
                      "url": "https://maps.example/place"} | kw)


def maps_source(db, status="available"):
    db.add(SourceConfig(key="google_maps", name="Google Maps", status=status))
    db.commit()


def test_clean_phone_and_parse_hours():
    assert clean_phone("Phone: +1 941-766-4122 ") == "941-766-4122"
    assert clean_phone("Phone: (863) 676 1433") == "863-676-1433"
    assert clean_phone("Phone: ") is None
    rows = ["5 4 3 2 1", "SaturdayClosed", "Friday8 AM–5 PM", "MondayOpen 24 hours"]
    assert parse_hours(rows) == [{"day": "Monday", "hours": "Open 24 hours"}, {"day": "Friday", "hours": "8 AM–5 PM"},
                                 {"day": "Saturday", "hours": "Closed"}]


def test_street_tokens_ignore_unit_case_and_suffix_spelling():
    assert street_tokens("2000 S PALESTINE ST STE 4") == street_tokens("2000 South Palestine Street, Athens, TX") == ["2000", "s", "palestine", "st"]


def test_matches_needs_street_city_and_state(db):
    loc = hospital(db).locations
    assert matches(loc, listing())
    assert not matches(loc, listing(address="2501 Harbor Blvd, Port Charlotte, FL 33952"))
    assert not matches(loc, listing(address="2500 Harbor Blvd, Punta Gorda, FL 33950"))
    assert not matches(loc, listing(address="2500 Harbor Blvd, Port Charlotte, GA 33952"))
    assert not matches(loc, listing(address=None))


def test_maps_url_searches_name_plus_address(db):
    o = hospital(db)
    url = maps_url(o, o.locations)
    assert url.startswith("https://www.google.com/maps/search/?api=1&query=ADVENTHEALTH+PORT+CHARLOTTE+INC+2500+HARBOR+BLVD")
    assert url.endswith("FL+33952")


def test_matched_listing_stores_phone_hours_and_link_and_keeps_npi_phone(db):
    o = hospital(db, phone="941-000-0000")
    assert enrich_maps(db, o, lookup=lambda url: listing()) == "matched"
    db.commit()
    p = db.scalars(select(OrganizationPhone)).one()
    assert (p.phone, p.source_key, p.source_url, p.differs_from_npi) == ("941-766-4122", "google_maps", "https://maps.example/place", True)
    assert p.collected_at is not None
    assert o.phone == "941-000-0000" and o.hours["weekly"] == HOURS and o.hours["source_key"] == "google_maps"
    assert o.maps_url.startswith("https://www.google.com/maps/search/") and o.maps_checked_at is not None


def test_same_phone_is_not_flagged(db):
    o = hospital(db, phone="(941) 766-4122")
    enrich_maps(db, o, lookup=lambda url: listing())
    assert db.scalars(select(OrganizationPhone)).one().differs_from_npi is False


def test_wrong_place_stores_nothing_and_keeps_old_hours(db):
    o = hospital(db)
    enrich_maps(db, o, lookup=lambda url: listing())
    db.commit()
    assert enrich_maps(db, o, lookup=lambda url: listing(address="1 Other St, Port Charlotte, FL")) == "no_match"
    db.commit()
    assert db.scalars(select(OrganizationPhone)).all() == []  # a stale Maps phone is not kept after a failed match
    assert o.hours is not None and o.maps_status == "no_match"


def test_empty_hours_do_not_erase_earlier_hours(db):
    o = hospital(db)
    enrich_maps(db, o, lookup=lambda url: listing())
    enrich_maps(db, o, lookup=lambda url: listing(hours=[]))
    assert o.hours["weekly"] == HOURS


def test_no_listing_and_no_address(db):
    o = hospital(db)
    assert enrich_maps(db, o, lookup=lambda url: None) == "no_match"
    bare = Organization(npi="9", name="No Address", organization_type="hospital", state="FL")
    db.add(bare)
    db.commit()
    assert enrich_maps(db, bare, lookup=lambda url: pytest.fail("no address means no lookup")) == "no_match"


def test_lead_api_lists_npi_phone_first_then_maps_phone(client, db):
    maps_source(db)
    o = hospital(db, phone="941-000-0000")
    client.app.dependency_overrides[maps_lookup] = lambda: (lambda url: listing())
    r = client.post(f"/api/leads/{o.id}/maps")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(p["source_key"], p["phone"], p["differs_from_npi"]) for p in body["phones"]] == [
        ("npi_registry", "941-000-0000", False), ("google_maps", "941-766-4122", True)]
    assert body["maps_status"] == "matched" and body["hours"]["weekly"] == HOURS and body["maps_url"].startswith("https://www.google.com/maps/")
    assert [p["source_key"] for p in client.get(f"/api/leads/{o.id}").json()["phones"]] == ["npi_registry", "google_maps"]


def test_hospital_without_lookup_still_shows_map_link_but_practice_does_not(client, db):
    h, p = hospital(db), hospital(db, npi="2", type_="practice")
    assert client.get(f"/api/leads/{h.id}").json()["maps_url"].startswith("https://www.google.com/maps/")
    assert client.get(f"/api/leads/{p.id}").json()["maps_url"] is None


def test_api_refuses_practices_and_unavailable_source(client, db):
    p = hospital(db, type_="practice")
    h = hospital(db, npi="2")
    maps_source(db, "approved_not_built")
    assert client.post(f"/api/leads/{p.id}/maps").status_code == 422
    assert client.post(f"/api/leads/{h.id}/maps").status_code == 422


def test_api_reports_block_and_failure_without_changing_the_lead(client, db):
    maps_source(db)
    o = hospital(db)

    def blocked(url):
        raise MapsBlocked("captcha")

    client.app.dependency_overrides[maps_lookup] = lambda: blocked
    assert client.post(f"/api/leads/{o.id}/maps").status_code == 503
    client.app.dependency_overrides[maps_lookup] = lambda: (lambda url: 1 / 0)
    assert client.post(f"/api/leads/{o.id}/maps").status_code == 502
    db.refresh(o)
    assert o.maps_status == "not_run" and db.scalars(select(OrganizationPhone)).all() == []


def test_batch_run_stops_on_block_and_marks_failures_retryable(session_factory, db):
    maps_source(db)
    for i in range(1, 5):
        hospital(db, npi=str(i))
    calls = []

    def get(url):
        calls.append(url)
        if len(calls) == 2:
            raise ValueError("boom")
        if len(calls) == 4:
            raise MapsBlocked("captcha")
        return listing()

    counts = run(session_factory, limit=10, get=get, sleep=lambda s: None)
    assert counts == {"matched": 2, "no_match": 0, "failed": 1, "blocked": 1} and len(calls) == 4
    db.expire_all()
    status = sorted(db.scalars(select(Organization.maps_status)))
    assert status == ["failed", "matched", "matched", "not_run"]
    assert run(session_factory, limit=10, get=lambda u: listing(), sleep=lambda s: None)["matched"] == 2  # the failed and the blocked one retry, matched stay


def test_listing_at_the_mailing_address_is_not_a_match(db):
    o = hospital(db)
    db.add(Location(organization_id=o.id, purpose="mailing", address_1="PO BOX 9", city="PORT CHARLOTTE", state="FL", zip="33949"))
    db.commit()
    db.refresh(o)
    assert enrich_maps(db, o, lookup=lambda url: listing(address="PO Box 9, Port Charlotte, FL 33949")) == "no_match"
