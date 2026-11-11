from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import CRM_STATUSES
from app.db import get_session
from app.models import Organization as O
from app.schemas import PipelineBoard, PipelineCard, PipelineColumn

router = APIRouter(prefix="/api/pipeline")

Status = Literal[CRM_STATUSES]  # type: ignore[valid-type]
ORDER = (O.fit_score.desc().nulls_last(), O.name, O.id)


def _counts(session: Session) -> dict[str, int]:
    return dict(session.execute(select(O.crm_status, func.count()).group_by(O.crm_status)).all())


@router.get("", response_model=PipelineBoard)
def board(limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)):
    counts = _counts(session)
    # One query: rank cards inside each status, keep the first `limit` of each.
    rn = func.row_number().over(partition_by=O.crm_status, order_by=ORDER).label("rn")
    r = select(O.crm_status, O.id, O.name, O.city, O.state, O.organization_type, O.fit_score, O.priority,
               O.next_follow_up_at, O.last_contacted_at, rn).subquery()
    rows = session.execute(select(r).where(r.c.rn <= limit).order_by(r.c.crm_status, r.c.rn))
    by_status: dict[str, list[PipelineCard]] = {s: [] for s in CRM_STATUSES}
    for row in rows:
        by_status[row.crm_status].append(PipelineCard.model_validate(row, from_attributes=True))
    return PipelineBoard(columns=[PipelineColumn(status=s, count=counts.get(s, 0), leads=by_status[s]) for s in CRM_STATUSES])


@router.get("/{status}", response_model=PipelineColumn)
def column(status: Status, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
           session: Session = Depends(get_session)):
    stmt = select(O).where(O.crm_status == status).order_by(*ORDER).limit(limit).offset(offset)
    leads = [PipelineCard.model_validate(o) for o in session.scalars(stmt)]
    return PipelineColumn(status=status, count=_counts(session).get(status, 0), leads=leads)
