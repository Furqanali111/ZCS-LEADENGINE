"""CMS NPI Registry connector. Pure: no database, no settings, no sleeping or retrying."""
import re
from dataclasses import dataclass

import httpx

API_URL = "https://npiregistry.cms.hhs.gov/api/"
PAGE_SIZE = 200
MAX_SKIP = 1000  # the API silently repeats the last page beyond this


class SourceError(Exception):
    pass


@dataclass
class NormalizedLead:
    npi: str
    name: str
    dba_name: str | None
    organization_type: str
    parent_organization_name: str | None
    primary_taxonomy_code: str | None
    primary_taxonomy_desc: str | None
    phone: str | None
    fax: str | None
    city: str | None
    state: str | None
    locations: list[dict]
    contact: dict | None
    practice_location_count: int
    active: bool
    sole_proprietor: bool
    raw: dict


def digits(phone: str | None) -> str | None:
    return re.sub(r"\D", "", phone or "") or None


def fetch_page(client: httpx.Client, *, enumeration_type: str, specialty: str,
               state: str, city: str | None, skip: int) -> list[dict]:
    if skip > MAX_SKIP:
        raise ValueError(f"skip {skip} exceeds the API cap of {MAX_SKIP}")
    params = {"version": "2.1", "enumeration_type": enumeration_type,
              "taxonomy_description": specialty, "state": state, "limit": PAGE_SIZE, "skip": skip}
    if city:
        params["city"] = city
    resp = client.get(API_URL, params=params)
    if resp.status_code != 200:
        raise SourceError(f"NPI Registry returned HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError as e:
        raise SourceError("NPI Registry returned a non-JSON body") from e
    if body.get("Errors"):
        raise SourceError(f"NPI Registry error: {body['Errors']}")
    return body.get("results") or []


def _title(s: str | None) -> str | None:
    return s.strip().title() if s and s.strip() else None


def normalize(raw: dict) -> NormalizedLead:
    basic = raw.get("basic") or {}
    is_person = raw.get("enumeration_type") == "NPI-1"
    taxonomies = raw.get("taxonomies") or []
    tax = next((t for t in taxonomies if t.get("primary")), taxonomies[0] if taxonomies else None)
    code = tax.get("code") if tax else None

    addresses = raw.get("addresses") or []
    loc = next((a for a in addresses if a.get("address_purpose") == "LOCATION"), None)

    def shape(a: dict, purpose: str, primary: bool) -> dict:
        return {"purpose": purpose, "address_1": a.get("address_1"), "address_2": a.get("address_2"),
                "city": a.get("city"), "state": a.get("state"),
                "zip": (digits(a.get("postal_code")) or "")[:5] or None,
                "phone": digits(a.get("telephone_number")), "is_primary": primary}

    purposes = {"LOCATION": "location", "MAILING": "mailing"}  # spec vocabulary, see ck_locations_purpose
    locations = [shape(a, purposes.get(a.get("address_purpose"), "mailing"), a is loc) for a in addresses]
    locations += [shape(a, "practice", False) for a in raw.get("practiceLocations") or []]
    phone = digits(loc.get("telephone_number")) if loc else None

    if is_person:
        cred = basic.get("credential")
        base = " ".join(p for p in (_title(basic.get("first_name")), _title(basic.get("last_name"))) if p)
        name = f"{base}, {cred.replace('.', '').strip().upper()}" if cred and cred.replace(".", "").strip() else base
        contact = {"first_name": _title(basic.get("first_name")), "last_name": _title(basic.get("last_name")),
                   "title": cred, "phone": phone, "role": "provider"}
        org_type = "solo_provider"
        parent = None
    else:
        name = basic.get("organization_name") or ""
        official = basic.get("authorized_official_first_name") or basic.get("authorized_official_last_name")
        contact = ({"first_name": _title(basic.get("authorized_official_first_name")),
                    "last_name": _title(basic.get("authorized_official_last_name")),
                    "title": basic.get("authorized_official_title_or_position"),
                    "phone": digits(basic.get("authorized_official_telephone_number")),
                    "role": "authorized_official"} if official else None)
        subpart = basic.get("organizational_subpart") == "YES"
        org_type = "hospital" if (code or "").startswith("28") else "subpart" if subpart else "practice"
        parent = basic.get("parent_organization_legal_business_name") if subpart else None

    dba = next((o.get("organization_name") for o in raw.get("other_names") or []
                if o.get("type") == "Doing Business As"), None)

    return NormalizedLead(
        npi=str(raw.get("number")), name=name, dba_name=dba, organization_type=org_type,
        parent_organization_name=parent, primary_taxonomy_code=code,
        primary_taxonomy_desc=tax.get("desc") if tax else None, phone=phone,
        fax=digits(loc.get("fax_number")) if loc else None,
        city=loc.get("city") if loc else None, state=loc.get("state") if loc else None,
        locations=locations, contact=contact,
        practice_location_count=len(raw.get("practiceLocations") or []),
        active=basic.get("status") == "A", sole_proprietor=basic.get("sole_proprietor") == "YES",
        raw=raw)
