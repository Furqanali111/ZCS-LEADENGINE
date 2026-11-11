from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import LeadScore, Organization
from app.services.scoring import ScoreResult


def save_score(session: Session, org: Organization, result: ScoreResult) -> None:
    """Upserts the organization's one current lead_scores row and copies total and priority onto it."""
    values = {"components": result.components, "total": result.total, "priority": result.priority,
              "config_version": result.config_version, "calculated_at": func.now()}
    stmt = insert(LeadScore).values(organization_id=org.id, **values)
    session.execute(stmt.on_conflict_do_update(
        index_elements=[LeadScore.organization_id], set_={**values, "updated_at": func.now()}))
    org.fit_score, org.priority = result.total, result.priority
