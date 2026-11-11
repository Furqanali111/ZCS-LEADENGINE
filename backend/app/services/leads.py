from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import LeadScore, Organization, SearchJobLead
from app.schemas import LeadFilters
from app.services.scoring import ScoreResult


def save_score(session: Session, org: Organization, result: ScoreResult) -> None:
    """Upserts the organization's one current lead_scores row and copies total and priority onto it."""
    values = {"components": result.components, "total": result.total, "priority": result.priority,
              "config_version": result.config_version, "calculated_at": func.now()}
    stmt = insert(LeadScore).values(organization_id=org.id, **values)
    session.execute(stmt.on_conflict_do_update(
        index_elements=[LeadScore.organization_id], set_={**values, "updated_at": func.now()}))
    org.fit_score, org.priority = result.total, result.priority


def _contains(column, text: str):
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def lead_query(filters: LeadFilters) -> Select:
    """Organizations matching the filters. No ordering or paging: the caller adds those."""
    o = Organization
    stmt = select(o)
    if filters.q and filters.q.strip():
        q = filters.q.strip()
        stmt = stmt.where(or_(*(_contains(c, q) for c in (o.name, o.dba_name, o.city, o.npi))))
    if filters.specialty and filters.specialty.strip():
        stmt = stmt.where(_contains(o.primary_taxonomy_desc, filters.specialty.strip()))
    for col, val in ((o.state, filters.state), (o.organization_type, filters.organization_type),
                     (o.priority, filters.priority), (o.crm_status, filters.crm_status)):
        if val is not None:
            stmt = stmt.where(col == val)
    if filters.min_score is not None:
        stmt = stmt.where(o.fit_score >= filters.min_score)
    if filters.search_job_id is not None:
        stmt = stmt.where(o.id.in_(
            select(SearchJobLead.organization_id).where(SearchJobLead.search_job_id == filters.search_job_id)))
    return stmt
