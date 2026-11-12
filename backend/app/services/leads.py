from datetime import date

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.constants import CLOSED_STATUSES
from app.models import Contact, LeadScore, Organization, SearchJobLead, SourceRecord
from app.schemas import LeadFilters
from app.services.scoring import ScoreResult, load_config, score
from app.sources.npi_registry import normalize


def save_score(session: Session, org: Organization, result: ScoreResult) -> None:
    """Upserts the organization's one current lead_scores row and copies total and priority onto it."""
    values = {"components": result.components, "total": result.total, "priority": result.priority,
              "config_version": result.config_version, "calculated_at": func.now()}
    stmt = insert(LeadScore).values(organization_id=org.id, **values)
    session.execute(stmt.on_conflict_do_update(
        index_elements=[LeadScore.organization_id], set_={**values, "updated_at": func.now()}))
    org.fit_score, org.priority = result.total, result.priority


_TITLED_STAFF = (Contact.role == "staff", Contact.title.is_not(None), Contact.title != "")


def has_titled_staff(session: Session, org_id) -> bool:
    return session.scalars(select(Contact.id).where(Contact.organization_id == org_id, *_TITLED_STAFF).limit(1)).first() is not None


def npis_with_titled_staff(session: Session, npis: list[str]) -> set[str]:
    if not npis:
        return set()
    return set(session.scalars(select(Organization.npi).join(Contact, Contact.organization_id == Organization.id)
                               .where(Organization.npi.in_(npis), *_TITLED_STAFF)))


_HAS_EMAIL = (Contact.email.is_not(None), Contact.email != "")


def has_email(session: Session, org_id) -> bool:
    return session.scalars(select(Contact.id).where(Contact.organization_id == org_id, *_HAS_EMAIL).limit(1)).first() is not None


def npis_with_email(session: Session, npis: list[str]) -> set[str]:
    if not npis:
        return set()
    return set(session.scalars(select(Organization.npi).join(Contact, Contact.organization_id == Organization.id)
                               .where(Organization.npi.in_(npis), *_HAS_EMAIL)))


def rescore_org(session: Session, org: Organization, config: dict | None = None) -> bool:
    """Recomputes the fit score from the stored NPI record plus website staff. False when there is no source record."""
    rec = session.scalars(select(SourceRecord).where(SourceRecord.organization_id == org.id)
                          .order_by(SourceRecord.collected_at.desc()).limit(1)).first()
    if rec is None:
        return False
    session.flush()
    save_score(session, org, score(normalize(rec.raw), config or load_config(),
                                   staff_with_title=has_titled_staff(session, org.id),
                                   email_found=has_email(session, org.id)))
    return True


def sorted_contacts(org: Organization) -> list[Contact]:
    return sorted(org.contacts, key=lambda c: (c.collected_at is None, c.collected_at or 0, c.id))


def primary_email(org: Organization) -> str | None:
    """Email of the first general contact, else the first contact with an email."""
    with_email = [c for c in sorted_contacts(org) if c.email]
    return next((c.email for c in with_email if c.role == "general"), with_email[0].email if with_email else None)


def _contains(column, text: str):
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def lead_query(filters: LeadFilters) -> Select:
    """Organizations matching the filters. No ordering or paging: the caller adds those."""
    o = Organization
    stmt = select(o)
    if filters.q and filters.q.strip():
        q = filters.q.strip()
        by_contact = exists().where(Contact.organization_id == o.id,
                                    or_(_contains(Contact.first_name, q), _contains(Contact.last_name, q),
                                           _contains(Contact.first_name + " " + Contact.last_name, q)))
        stmt = stmt.where(or_(*(_contains(c, q) for c in (o.name, o.dba_name, o.city, o.npi)), by_contact))
    if filters.specialty and filters.specialty.strip():
        stmt = stmt.where(_contains(o.primary_taxonomy_desc, filters.specialty.strip()))
    for col, val in ((o.state, filters.state), (o.organization_type, filters.organization_type),
                     (o.priority, filters.priority), (o.crm_status, filters.crm_status)):
        if val is not None:
            stmt = stmt.where(col == val)
    if filters.owner:
        stmt = stmt.where(o.owner.is_(None) if filters.owner == "none" else func.lower(o.owner) == filters.owner.lower())
    if filters.min_score is not None:
        stmt = stmt.where(o.fit_score >= filters.min_score)
    if filters.search_job_id is not None:
        stmt = stmt.where(o.id.in_(
            select(SearchJobLead.organization_id).where(SearchJobLead.search_job_id == filters.search_job_id)))
    if filters.has_website is not None:
        stmt = stmt.where(o.website.is_not(None) if filters.has_website else o.website.is_(None))
    if filters.has_email is not None:
        has = exists().where(Contact.organization_id == o.id, Contact.email.is_not(None))
        stmt = stmt.where(has if filters.has_email else ~has)
    if filters.follow_up == "none":
        stmt = stmt.where(o.next_follow_up_at.is_(None))
    elif filters.follow_up:
        today = date.today()  # local date, computed once per query
        due = o.next_follow_up_at < today if filters.follow_up == "overdue" else o.next_follow_up_at <= today
        stmt = stmt.where(due, o.crm_status.not_in(CLOSED_STATUSES))
    return stmt
