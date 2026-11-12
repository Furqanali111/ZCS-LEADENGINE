from dataclasses import replace

import pytest

from app.services.scoring import load_config, priority_for, score
from app.sources.npi_registry import normalize

CONFIG = load_config()


def lead(**over):
    base = normalize({
        "number": "1234567890", "enumeration_type": "NPI-2",
        "basic": {"organization_name": "Acme Care", "status": "A",
                  "authorized_official_first_name": "JANE", "authorized_official_last_name": "DOE",
                  "authorized_official_title_or_position": "ADMINISTRATOR",
                  "authorized_official_telephone_number": "555-222-3333"},
        "addresses": [{"address_purpose": "LOCATION", "address_1": "1 Main", "city": "Miami",
                       "state": "FL", "postal_code": "331010000", "telephone_number": "555-111-2222"}],
        "taxonomies": [{"code": "207Q00000X", "desc": "Family Medicine", "primary": True}],
        "other_names": [], "practiceLocations": []})
    return replace(base, **over)


def sparse():
    return normalize({"number": "1234567890", "enumeration_type": "NPI-2",
                      "basic": {"organization_name": "X", "status": "A"}, "addresses": [],
                      "taxonomies": [], "other_names": [], "practiceLocations": []})


def test_core_independent_practice_full_contact():
    r = score(lead(), CONFIG)
    assert (r.total, r.priority, r.config_version) == (90, "high", "3")


def test_subspecialty_subpart():
    base = lead()
    l = replace(base, primary_taxonomy_code="207RR0500X", organization_type="subpart",
                contact={**base.contact, "phone": base.phone})
    r = score(l, CONFIG)
    assert (r.total, r.priority) == (55, "low")


def test_hospital():
    base = lead()
    l = replace(base, primary_taxonomy_code="282N00000X", organization_type="hospital",
                contact={**base.contact, "phone": base.phone})
    r = score(l, CONFIG)
    assert (r.total, r.priority) == (34, "low")


def test_solo_provider_core():
    l = lead(organization_type="solo_provider",
             contact={"first_name": "Jane", "last_name": "Smith", "title": "MD", "phone": "5551234567",
                      "role": "provider"})
    r = score(l, CONFIG)
    assert (r.total, r.priority) == (81, "medium")
    assert r.components["independence"]["reason"] == "self-reported sole proprietor"
    assert r.components["contactability"]["points"] == 10


def test_multi_location_adds_ten():
    r = score(lead(practice_location_count=2), CONFIG)
    assert r.components["multi_location"]["points"] == 10
    assert r.total == 100


def test_missing_everything_scores_independence_only():
    r = score(sparse(), CONFIG)
    assert (r.total, r.priority) == (20, "low")
    assert r.components["independence"]["reason"].endswith("size unknown from this source")
    assert r.components["multi_location"]["reason"] == "provider count not available from this source"
    assert set(r.components) == set(CONFIG["max"])
    assert all(c["reason"] for c in r.components.values())


@pytest.mark.parametrize("total,priority", [(95, "critical"), (94, "high"), (90, "high"),
                                            (89, "medium"), (80, "medium"), (79, "low")])
def test_priority_boundaries(total, priority):
    assert priority_for(total, CONFIG) == priority


def test_name_only_official_gets_five():
    base = lead()
    r = score(lead(contact={**base.contact, "title": None}), CONFIG)
    assert r.components["decision_maker"]["points"] == 5


def test_max_points_sum_to_100():
    assert sum(CONFIG["max"].values()) == 100


def test_staff_with_title_counts_as_decision_maker():
    base = lead()
    l = lead(contact={**base.contact, "first_name": None, "last_name": None, "title": None})
    assert score(l, CONFIG).components["decision_maker"]["points"] == 0
    dm = score(l, CONFIG, staff_with_title=True).components["decision_maker"]
    assert dm["points"] == 10
    assert dm["reason"] == "named staff member with title found on practice website"


def test_staff_flag_does_not_override_official_or_solo():
    assert score(lead(), CONFIG, staff_with_title=True).components["decision_maker"]["reason"] == "authorized official with name and title"
    base = lead()
    name_only = lead(contact={**base.contact, "title": None})
    assert score(name_only, CONFIG, staff_with_title=True).components["decision_maker"]["points"] == 10
    solo = lead(organization_type="solo_provider", contact={"first_name": "J", "last_name": "S", "title": "MD", "phone": "1", "role": "provider"})
    assert score(solo, CONFIG, staff_with_title=True).components["decision_maker"]["reason"].startswith("solo")


def test_config_version_is_3():
    assert CONFIG["version"] == "3"
