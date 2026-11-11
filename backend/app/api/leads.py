import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.errors import AppError
from app.models import LeadActivity, Organization, SourceRecord
from app.schemas import ActivityIn, ActivityOut, ActivityPage, LeadFilters, LeadOut, LeadPage, LeadPatch
from app.services.activities import add_activity, change_status
from app.services.leads import lead_query
from app.services.suppression import suppressed_ids

router = APIRouter(prefix="/api/leads")

SORTS = {"score": Organization.fit_score, "name": Organization.name, "updated": Organization.updated_at}
LOADS = (selectinload(Organization.contacts), selectinload(Organization.locations),
         selectinload(Organization.score), selectinload(Organization.source_records).defer(SourceRecord.raw))
PLAIN = [f for f in LeadOut.model_fields if f not in ("contact", "locations", "score", "source", "suppressed")]


def _out(org: Organization, suppressed: bool = False) -> LeadOut:
    by_role = {c.role: c for c in org.contacts}
    src = max(org.source_records, key=lambda s: s.collected_at, default=None)
    return LeadOut.model_validate({
        **{f: getattr(org, f) for f in PLAIN},
        "contact": by_role.get("authorized_official") or by_role.get("provider"),
        "locations": org.locations,
        "score": org.score,
        "suppressed": suppressed,
        "source": {"source_key": src.source_key, "collected_at": src.collected_at} if src else None,
    }, from_attributes=True)


@router.get("", response_model=LeadPage)
def list_leads(filters: Annotated[LeadFilters, Query()], session: Session = Depends(get_session),
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
               sort: Literal["score", "name", "updated"] = "score", order: Literal["asc", "desc"] = "desc"):
    base = lead_query(filters)
    total = session.scalar(select(func.count()).select_from(base.subquery()))
    col = SORTS[sort]
    col = col.asc().nulls_last() if order == "asc" else col.desc().nulls_last()
    stmt = base.options(*LOADS).order_by(col, Organization.id).limit(page_size).offset((page - 1) * page_size)
    orgs = session.scalars(stmt).all()
    hit = suppressed_ids(session, [o.id for o in orgs])
    return LeadPage(items=[_out(o, o.id in hit) for o in orgs], total=total, page=page, page_size=page_size)


def _load(session: Session, lead_id: str, options=()) -> Organization:
    try:
        org = session.get(Organization, uuid.UUID(lead_id), options=options)
    except ValueError:
        org = None
    if org is None:
        raise AppError(404, "not_found", f"Lead {lead_id} not found")
    return org


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: str, session: Session = Depends(get_session)):
    org = _load(session, lead_id, LOADS)
    return _out(org, bool(suppressed_ids(session, [org.id])))


@router.patch("/{lead_id}", response_model=LeadOut)
def patch_lead(lead_id: str, body: LeadPatch, session: Session = Depends(get_session)):
    org = _load(session, lead_id, LOADS)
    if body.crm_status is not None:
        change_status(session, org, body.crm_status)
    if "next_follow_up_at" in body.model_fields_set:
        org.next_follow_up_at = body.next_follow_up_at
    session.commit()
    session.refresh(org)  # reload server-side updated_at
    return _out(org, bool(suppressed_ids(session, [org.id])))


@router.get("/{lead_id}/activities", response_model=ActivityPage)
def list_activities(lead_id: str, session: Session = Depends(get_session),
                    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    org = _load(session, lead_id)
    where = LeadActivity.organization_id == org.id
    total = session.scalar(select(func.count()).select_from(LeadActivity).where(where))
    stmt = (select(LeadActivity).where(where).order_by(LeadActivity.occurred_at.desc(), LeadActivity.created_at.desc(), LeadActivity.id)
            .limit(page_size).offset((page - 1) * page_size))
    return ActivityPage(items=session.scalars(stmt).all(), total=total, page=page, page_size=page_size)


@router.post("/{lead_id}/activities", response_model=ActivityOut, status_code=201)
def create_activity(lead_id: str, body: ActivityIn, session: Session = Depends(get_session)):
    org = _load(session, lead_id)
    act = add_activity(session, org, type=body.type, occurred_at=body.occurred_at, summary=body.summary, outcome=body.outcome)
    if "next_follow_up_at" in body.model_fields_set:
        org.next_follow_up_at = body.next_follow_up_at
    session.commit()
    return act
