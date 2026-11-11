from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import LeadActivity, Organization

CONTACT_TYPES = ("call", "email", "meeting")


def add_activity(session: Session, org: Organization, *, type: str, occurred_at: datetime | None = None,
                 summary: str | None = None, outcome: str | None = None,
                 from_status: str | None = None, to_status: str | None = None) -> LeadActivity:
    """Adds without committing, so the caller keeps activity and snapshot in one transaction."""
    occurred_at = occurred_at or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    act = LeadActivity(organization_id=org.id, type=type, occurred_at=occurred_at, summary=summary,
                       outcome=outcome, from_status=from_status, to_status=to_status)
    session.add(act)
    if type in CONTACT_TYPES and (org.last_contacted_at is None or occurred_at > org.last_contacted_at):
        org.last_contacted_at = occurred_at
    return act


def change_status(session: Session, org: Organization, new_status: str) -> bool:
    if org.crm_status == new_status:
        return False
    now = datetime.now(timezone.utc)
    add_activity(session, org, type="status_change", occurred_at=now, from_status=org.crm_status, to_status=new_status)
    org.crm_status, org.status_updated_at = new_status, now
    return True
