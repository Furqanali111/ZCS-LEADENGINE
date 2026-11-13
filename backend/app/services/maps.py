"""Google Maps enrichment: find the listing for a hospital, store its phone and hours with their source and the map link."""
import re
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import quote_plus

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Location, Organization, OrganizationPhone
from app.sources.gmaps import Listing

SOURCE_KEY = "google_maps"
PURPOSES = ("practice", "location", "mailing")  # first one the lead has wins
SUFFIX = {"street": "st", "road": "rd", "boulevard": "blvd", "avenue": "ave", "drive": "dr", "highway": "hwy", "lane": "ln",
          "parkway": "pkwy", "court": "ct", "place": "pl", "north": "n", "south": "s", "east": "e", "west": "w"}
UNIT = re.compile(r"\b(ste|suite|unit|bldg|building|floor|fl|rm|room)\b.*$|#.*$")


def street_tokens(address: str | None) -> list[str]:
    s = UNIT.sub("", (address or "").lower().split(",")[0])
    return [SUFFIX.get(w, w) for w in re.sub(r"[^a-z0-9 ]", " ", s).split()]


def pick_location(locations: list[Location]) -> Location | None:
    return next((l for p in PURPOSES for l in locations if l.purpose == p and l.address_1), None)


def maps_url(org: Organization, locations: list[Location]) -> str | None:
    """Maps search on the lead's name plus its street address. A bare address link lands on a street pin, not the hospital."""
    loc = pick_location(locations)
    if loc is None:
        return None
    name = re.sub(r"[,.]?\s*\b(inc|llc|l\.l\.c|pc|pllc|pa|corp|ltd|lp)\b\.?", "", org.dba_name or org.name, flags=re.I).strip()  # a legal suffix makes Maps return a list
    query = " ".join(x for x in (name, loc.address_1, loc.city, loc.state, (loc.zip or "")[:5]) if x)
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def digits(phone: str | None) -> str:
    return re.sub(r"^1(?=\d{10}$)", "", re.sub(r"\D", "", phone or ""))


def matches(locations: list[Location], listing: Listing) -> bool:
    """Conservative: the listing's street number and street name, city and state all agree with one of the lead's addresses.
    The name is not compared: NPI legal names often differ from the name on the map."""
    addr = (listing.address or "").lower()
    got = street_tokens(addr)
    for loc in locations:
        want = street_tokens(loc.address_1)
        if (len(want) >= 2 and want[0].isdigit() and got[: len(want)] == want and loc.city and loc.city.lower() in addr
                and loc.state and re.search(rf"\b{loc.state.lower()}\b", addr)):
            return True
    return False


def enrich_maps(session: Session, org: Organization, *, lookup: Callable[[str], Listing | None],
                now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> str:
    """Returns the new maps_status. The NPI phone is never touched; a different Maps phone is stored beside it and flagged."""
    url = maps_url(org, org.locations)
    stamp = now()
    org.maps_url = url  # kept so a salesperson can open the same search and check the number by hand
    org.maps_checked_at = stamp
    listing = lookup(url) if url else None
    session.execute(delete(OrganizationPhone).where(OrganizationPhone.organization_id == org.id, OrganizationPhone.source_key == SOURCE_KEY))
    if listing is None or not matches([pick_location(org.locations)], listing):  # only the address that was searched
        org.maps_status = "no_match"
        return org.maps_status
    if listing.phone:
        session.add(OrganizationPhone(organization_id=org.id, phone=listing.phone, source_key=SOURCE_KEY, source_url=listing.url,
                                      collected_at=stamp, differs_from_npi=bool(org.phone) and digits(listing.phone) != digits(org.phone)))
    # no hours on the listing keeps the stored ones: an empty read must not erase a good earlier one
    if listing.hours:
        org.hours = {"weekly": listing.hours, "source_key": SOURCE_KEY, "source_url": listing.url, "collected_at": stamp.isoformat()}
    org.maps_status = "matched"
    return org.maps_status
