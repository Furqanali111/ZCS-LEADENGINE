import re
from collections.abc import Collection
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Organization, SuppressionEntry
from app.services.activities import change_status

DNC = "do_not_contact"


def normalize(kind: str, value: str) -> str:
    value = (value or "").strip()
    if kind == "email":
        value = value.lower()
        if value.count("@") != 1 or value.startswith("@") or value.endswith("@"):
            raise ValueError("Email must contain one @")
    elif kind in ("npi", "phone"):
        value = re.sub(r"\D", "", value)
        if kind == "npi" and len(value) != 10:
            raise ValueError("NPI must be 10 digits")
        if kind == "phone" and len(value) < 7:
            raise ValueError("Phone must have at least 7 digits")
    else:
        raise ValueError(f"Unknown kind {kind}")
    return value


def _digits(col):
    return func.regexp_replace(col, r"\D", "", "g")


def _matches():
    entry = SuppressionEntry
    return or_(
        exists().where(entry.kind == "npi", entry.value == Organization.npi),
        exists().where(entry.kind == "phone", entry.value.in_([_digits(Organization.phone), _digits(Organization.fax)])),
    )  # email entries match no lead until slice 3 stores emails


def suppressed_ids(session: Session, org_ids: Collection[UUID]) -> set[UUID]:
    if not org_ids:
        return set()
    return set(session.scalars(select(Organization.id).where(Organization.id.in_(org_ids), _matches())))


def _mark(session: Session, where) -> None:
    stmt = select(Organization).where(where, Organization.crm_status != DNC).execution_options(populate_existing=True)
    for org in session.scalars(stmt).all():
        change_status(session, org, DNC)


def enforce(session: Session, org_ids: Collection[UUID]) -> None:
    """Sets do_not_contact on every given org that matches the list, in one bulk query."""
    if org_ids:
        _mark(session, Organization.id.in_(org_ids) & _matches())


def add_entry(session: Session, kind: str, value: str, reason: str | None = None) -> SuppressionEntry:
    value = normalize(kind, value)
    if session.scalar(select(SuppressionEntry.id).where(SuppressionEntry.kind == kind, SuppressionEntry.value == value)):
        raise AppError(409, "already_suppressed", f"{kind} {value} is already suppressed")
    entry = SuppressionEntry(kind=kind, value=value, reason=reason)
    session.add(entry)
    session.flush()
    if kind == "npi":
        _mark(session, Organization.npi == value)
    elif kind == "phone":
        _mark(session, or_(_digits(Organization.phone) == value, _digits(Organization.fax) == value))
    session.commit()
    return entry
