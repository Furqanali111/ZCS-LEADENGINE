import json
from pathlib import Path

import httpx
import pytest

from app.sources.npi_registry import MAX_SKIP, SourceError, digits, fetch_page, normalize

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["results"]


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_digits():
    assert digits("903-614-8500") == "9036148500"
    assert digits("") is None
    assert digits(None) is None


def test_normalize_org_maps_core_fields():
    raw = load("npi2_page.json")[0]
    lead = normalize(raw)
    assert lead.npi == raw["number"]
    assert lead.name == raw["basic"]["organization_name"]
    loc = next(a for a in raw["addresses"] if a["address_purpose"] == "LOCATION")
    assert lead.phone == digits(loc["telephone_number"])
    assert lead.state == loc["state"]
    assert lead.contact["role"] == "authorized_official"
    assert lead.active is True and lead.sole_proprietor is False
    assert lead.practice_location_count == len(raw["practiceLocations"])
    assert lead.raw is raw


def test_normalize_subpart_sets_type_and_parent():
    raw = next(r for r in load("npi2_page.json") if r["basic"].get("organizational_subpart") == "YES")
    lead = normalize(raw)
    assert lead.organization_type == "subpart"
    assert lead.parent_organization_name == raw["basic"]["parent_organization_legal_business_name"]
    assert lead.dba_name == next((o["organization_name"] for o in raw["other_names"] if o["type"] == "Doing Business As"), None)


def test_normalize_hospital_by_taxonomy_prefix():
    raw = {"number": "1", "enumeration_type": "NPI-2",
           "basic": {"organization_name": "H", "status": "A", "organizational_subpart": "YES"},
           "addresses": [], "other_names": [], "practiceLocations": [],
           "taxonomies": [{"code": "282N00000X", "desc": "General Acute Care Hospital", "primary": True}]}
    assert normalize(raw).organization_type == "hospital"


def test_normalize_individual_builds_name():
    raw = next(r for r in load("npi1_page.json") if r["basic"].get("sole_proprietor") == "YES")
    lead = normalize(raw)
    assert lead.organization_type == "solo_provider"
    assert lead.sole_proprietor is True
    assert lead.name.endswith(", MD") or "," not in lead.name
    assert lead.name == lead.name.title().replace(", Md", ", MD")
    assert lead.contact["role"] == "provider" and lead.contact["phone"] == lead.phone


def test_normalize_individual_name_example():
    raw = {"number": "2", "enumeration_type": "NPI-1",
           "basic": {"first_name": "QUEENIE ANN", "last_name": "ABAD", "credential": "M.D.", "status": "A"},
           "addresses": [], "taxonomies": [], "other_names": [], "practiceLocations": []}
    assert normalize(raw).name == "Queenie Ann Abad, MD"


def test_normalize_sparse_record_does_not_crash():
    lead = normalize({"number": "1234567890", "enumeration_type": "NPI-2",
                      "basic": {"organization_name": "X", "status": "A"},
                      "addresses": [], "taxonomies": [], "other_names": [], "practiceLocations": []})
    assert lead.phone is None and lead.contact is None and lead.primary_taxonomy_code is None
    assert lead.organization_type == "practice" and lead.locations == []


def test_fetch_page_encodes_params():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"result_count": 1, "results": [{"number": "1"}]})

    out = fetch_page(client_for(handler), enumeration_type="NPI-2", specialty="Obstetrics & Gynecology",
                     state="TX", city="San Antonio", skip=200)
    assert out == [{"number": "1"}]
    assert seen == {"version": "2.1", "enumeration_type": "NPI-2",
                    "taxonomy_description": "Obstetrics & Gynecology", "state": "TX",
                    "city": "San Antonio", "limit": "200", "skip": "200"}


def test_fetch_page_omits_city_when_unset():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"results": []})

    fetch_page(client_for(handler), enumeration_type="NPI-1", specialty="x", state="TX", city=None, skip=0)
    assert "city" not in seen


def test_fetch_page_empty_results_returns_list():
    c = client_for(lambda r: httpx.Response(200, json={"result_count": 0, "results": []}))
    assert fetch_page(c, enumeration_type="NPI-2", specialty="x", state="TX", city=None, skip=0) == []


def test_fetch_page_api_error_raises():
    c = client_for(lambda r: httpx.Response(200, json={"Errors": [{"description": "bad"}]}))
    with pytest.raises(SourceError):
        fetch_page(c, enumeration_type="NPI-2", specialty="x", state="TX", city=None, skip=0)


def test_fetch_page_non_200_raises():
    c = client_for(lambda r: httpx.Response(503))
    with pytest.raises(SourceError):
        fetch_page(c, enumeration_type="NPI-2", specialty="x", state="TX", city=None, skip=0)


def test_fetch_page_refuses_skip_over_1000():
    c = client_for(lambda r: httpx.Response(200, json={"results": []}))
    with pytest.raises(ValueError):
        fetch_page(c, enumeration_type="NPI-2", specialty="x", state="TX", city=None, skip=MAX_SKIP + 1)
