import re
from urllib.parse import urlparse

from sqlalchemy import Integer, cast, exists, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.models import Contact, Organization
from app.services.suppression import _digits
from app.services.verify import registrable_domain

MAX_RELATED = 20
PG_SUFFIXES = r"\m(llc|inc|pc|pllc|pa|corp)\M"  # Postgres word bounds
PY_SUFFIXES = re.compile(r"\b(llc|inc|pc|pllc|pa|corp)\b")


def norm_name(name: str | None) -> str:
    s = PY_SUFFIXES.sub("", re.sub(r"[^a-z0-9 ]", "", (name or "").lower()))
    return re.sub(r"\s+", " ", s).strip()


def _sql_name(col):
    s = func.regexp_replace(func.lower(col), r"[^a-z0-9 ]", "", "g")
    return func.trim(func.regexp_replace(func.regexp_replace(s, PG_SUFFIXES, "", "g"), r"\s+", " ", "g"))


def site_domain(url: str | None) -> str:
    u = (url or "").strip()
    return registrable_domain(urlparse(u if "//" in u else f"//{u}").hostname or "") if u else ""


def related_leads(session: Session, org: Organization) -> list[dict]:
    """One query: each reason is a boolean column, rows with none are dropped. Website is confirmed in Python."""
    O = Organization
    off = Contact.role == "authorized_official"
    pairs = [(f.strip().lower(), l.strip().lower()) for f, l in session.execute(
        select(Contact.first_name, Contact.last_name).where(Contact.organization_id == org.id, off)) if f.strip() and l.strip()]
    digits = re.sub(r"^1(?=\d{10}$)", "", re.sub(r"\D", "", org.phone or ""))
    parent, name, domain = (org.parent_organization_name or "").strip().lower(), norm_name(org.name), site_domain(org.website)
    flags = {
        "same_phone": _digits(O.phone) == digits if digits else None,
        "same_name": _sql_name(O.name) == name if name else None,
        "same_parent": func.lower(func.trim(O.parent_organization_name)) == parent if parent else None,
        "same_official": exists().where(Contact.organization_id == O.id, off,
            tuple_(func.lower(func.trim(Contact.first_name)), func.lower(func.trim(Contact.last_name))).in_(pairs)) if pairs else None,
        "same_website": O.website.ilike(f"%{domain}%") if domain else None,
    }
    flags = {k: v for k, v in flags.items() if v is not None}
    if not flags:
        return []
    count = sum((cast(v, Integer) for k, v in flags.items() if k != "same_website"), cast(0, Integer))
    cols = [O.id, O.name, O.city, O.state, O.crm_status, O.owner, O.fit_score, O.priority]
    rows = session.execute(select(*cols, O.website, *[v.label(k) for k, v in flags.items()]).where(
        O.id != org.id, or_(*flags.values())).order_by(count.desc(), O.fit_score.desc().nulls_last()).limit(100)).mappings()
    out = []
    for r in rows:
        reasons = [k for k in flags if r[k] and (k != "same_website" or site_domain(r["website"]) == domain)]
        if reasons:
            out.append({c.key: r[c.key] for c in cols} | {"reasons": reasons})
    out.sort(key=lambda x: -len(x["reasons"]))  # stable: fit order kept within a tie
    return out[:MAX_RELATED]
