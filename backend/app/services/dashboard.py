from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import exists, func, literal_column, select, text
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session, aliased

from app.constants import CLOSED_STATUSES
from app.models import LeadActivity, Organization, SearchJob
from app.schemas import Conversion, DashboardStats, DateRange, JobOut, TeamRow

CONTACT_TYPES = ("call", "email", "meeting")


def _json_list(col, limit: int | None = None):
    """Scalar subquery: [{key, count}, ...] for the most common values of col, one round trip with everything else."""
    n = func.count()
    top = select(col.label("key"), n.label("count")).where(col.is_not(None)).group_by(col).order_by(n.desc(), col)
    if limit:
        top = top.limit(limit)
    t = top.subquery()
    obj = func.json_build_object("key", t.c.key, "count", t.c.count)
    return select(func.coalesce(func.json_agg(aggregate_order_by(obj, t.c.count.desc(), t.c.key)), text("'[]'::json"))).scalar_subquery()


def build_stats(session: Session, start: date, end: date, today: date) -> DashboardStats:
    O, A = Organization, LeadActivity
    # The range covers whole days, both ends included (UTC).
    lo = datetime.combine(start, time.min, tzinfo=timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    C = aliased(LeadActivity)
    # Numerator is a subset of the denominator: converted in range AND contacted in range.
    contact = exists().where(C.organization_id == A.organization_id, C.type.in_(CONTACT_TYPES),
                             C.occurred_at >= lo, C.occurred_at < hi)
    in_range = (A.occurred_at >= lo, A.occurred_at < hi)
    converted = select(func.count(func.distinct(A.organization_id))).where(
        A.type == "status_change", A.to_status == "converted", *in_range, contact).scalar_subquery()
    contacted = select(func.count(func.distinct(A.organization_id))).where(A.type.in_(CONTACT_TYPES), *in_range).scalar_subquery()
    day = datetime.combine(today, time.min, tzinfo=timezone.utc)
    changed_today = select(func.count(func.distinct(A.organization_id))).where(
        A.type == "status_change", A.occurred_at >= day, A.occurred_at < day + timedelta(days=1)).scalar_subquery()
    # Per salesperson, today only. Names are typed, so group ignoring case; no name means "Unknown".
    who = func.lower(func.coalesce(A.actor, "Unknown"))
    team = (select(func.max(func.coalesce(A.actor, "Unknown")).label("name"),
                   func.count().filter(A.type == "call").label("calls"),
                   func.count().filter(A.type == "email").label("emails"),
                   func.count().filter(A.type == "status_change").label("status_changes"))
            .where(A.type.in_(("call", "email", "status_change")), A.occurred_at >= day, A.occurred_at < day + timedelta(days=1))
            .group_by(who).subquery("team"))
    team_rows = select(func.coalesce(func.json_agg(aggregate_order_by(func.row_to_json(literal_column("team")), team.c.calls.desc(), team.c.name)),
                                     text("'[]'::json"))).select_from(team).scalar_subquery()
    J = aliased(SearchJob)
    recent = select(J).order_by(J.created_at.desc()).limit(5).subquery("recent")
    jobs = select(func.coalesce(func.json_agg(aggregate_order_by(func.row_to_json(literal_column("recent")), recent.c.created_at.desc())),
                                text("'[]'::json"))).select_from(recent).scalar_subquery()
    # One statement, one round trip (each costs ~150 ms to the hosted database): tiles from a single pass
    # over organizations, plus the top lists, jobs and conversion as scalar subqueries.
    total, new, crit, due, meet, conv, by_state, by_spec, by_status, job_rows, n_conv, n_contacted, n_changed, team_today = session.execute(select(
        func.count(),
        func.count().filter(O.crm_status == "new"),
        func.count().filter(O.priority.in_(("critical", "high"))),
        func.count().filter(O.next_follow_up_at <= today, O.crm_status.not_in(CLOSED_STATUSES)),
        func.count().filter(O.crm_status == "meeting_scheduled"),
        func.count().filter(O.crm_status == "converted"),
        _json_list(O.state, 10), _json_list(O.primary_taxonomy_desc, 10), _json_list(O.crm_status),
        jobs, converted, contacted, changed_today, team_rows,
    )).one()
    return DashboardStats(
        range=DateRange(from_=start, to=end), total=total, new_leads=new, critical_high=crit, follow_ups_due=due, status_changes_today=n_changed, team_today=[TeamRow.model_validate(r) for r in team_today],
        meetings_scheduled=meet, converted=conv,
        by_state=by_state, by_specialty=by_spec, by_status=by_status,
        recent_jobs=[JobOut.model_validate(j) for j in job_rows],
        conversion=Conversion(converted=n_conv, contacted=n_contacted, rate=n_conv / n_contacted if n_contacted else None),
    )
