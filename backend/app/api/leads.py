import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.errors import AppError
from app.models import Organization, SourceRecord
from app.schemas import LeadFilters, LeadOut, LeadPage, LeadPatch
from app.services.leads import lead_query

router = APIRouter(prefix="/api/leads")

SORTS = {"score": Organization.fit_score, "name": Organization.name, "updated": Organization.updated_at}
LOADS = (selectinload(Organization.contacts), selectinload(Organization.locations),
         selectinload(Organization.score), selectinload(Organization.source_records).defer(SourceRecord.raw))
PLAIN = [f for f in LeadOut.model_fields if f not in ("contact", "locations", "score", "source")]


def _out(org: Organization) -> LeadOut:
    by_role = {c.role: c for c in org.contacts}
    src = max(org.source_records, key=lambda s: s.collected_at, default=None)
    return LeadOut.model_validate({
        **{f: getattr(org, f) for f in PLAIN},
        "contact": by_role.get("authorized_official") or by_role.get("provider"),
        "locations": org.locations,
        "score": org.score,
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
    return LeadPage(items=[_out(o) for o in session.scalars(stmt)], total=total, page=page, page_size=page_size)


@router.patch("/{lead_id}", response_model=LeadOut)
def patch_lead(lead_id: str, body: LeadPatch, session: Session = Depends(get_session)):
    try:
        org = session.get(Organization, uuid.UUID(lead_id), options=LOADS)
    except ValueError:
        org = None
    if org is None:
        raise AppError(404, "not_found", f"Lead {lead_id} not found")
    org.crm_status, org.status_updated_at = body.crm_status, datetime.now(timezone.utc)
    session.commit()
    session.refresh(org)  # reload server-side updated_at
    return _out(org)
