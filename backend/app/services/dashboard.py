from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from app.constants import CLOSED_STATUSES
from app.models import LeadActivity, Organization, SearchJob
from app.schemas import Conversion, CountItem, DashboardStats, DateRange, JobOut

CONTACT_TYPES = ("call", "email", "meeting")


def _top(session: Session, col) -> list[CountItem]:
    n = func.count()
    rows = session.execute(select(col, n).where(col.is_not(None)).group_by(col).order_by(n.desc(), col).limit(10))
    return [CountItem(key=k, count=c) for k, c in rows]


def build_stats(session: Session, start: date, end: date, today: date) -> DashboardStats:
    O, A = Organization, LeadActivity
    # One pass over organizations for every tile.
    total, new, crit, due, meet, conv = session.execute(select(
        func.count(),
        func.count().filter(O.crm_status == "new"),
        func.count().filter(O.priority.in_(("critical", "high"))),
        func.count().filter(O.next_follow_up_at <= today, O.crm_status.not_in(CLOSED_STATUSES)),
        func.count().filter(O.crm_status == "meeting_scheduled"),
        func.count().filter(O.crm_status == "converted"),
    )).one()
    by_status = session.execute(select(O.crm_status, func.count()).group_by(O.crm_status).order_by(func.count().desc(), O.crm_status))
    # The range covers whole days, both ends included (UTC).
    lo = datetime.combine(start, time.min, tzinfo=timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    in_range = (A.occurred_at >= lo, A.occurred_at < hi)
    C = aliased(LeadActivity)
    # Numerator is a subset of the denominator: converted in range AND contacted in range.
    contact = exists().where(C.organization_id == A.organization_id, C.type.in_(CONTACT_TYPES),
                             C.occurred_at >= lo, C.occurred_at < hi)
    converted = session.scalar(select(func.count(func.distinct(A.organization_id))).where(
        A.type == "status_change", A.to_status == "converted", *in_range, contact))
    contacted = session.scalar(select(func.count(func.distinct(A.organization_id))).where(
        A.type.in_(CONTACT_TYPES), *in_range))
    jobs = session.scalars(select(SearchJob).order_by(SearchJob.created_at.desc()).limit(5))
    return DashboardStats(
        range=DateRange(from_=start, to=end), total=total, new_leads=new, critical_high=crit, follow_ups_due=due,
        meetings_scheduled=meet, converted=conv,
        by_state=_top(session, O.state), by_specialty=_top(session, O.primary_taxonomy_desc),
        by_status=[CountItem(key=k, count=c) for k, c in by_status],
        recent_jobs=[JobOut.model_validate(j) for j in jobs],
        conversion=Conversion(converted=converted, contacted=contacted, rate=converted / contacted if contacted else None),
    )
