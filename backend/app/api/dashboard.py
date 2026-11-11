from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import AppError
from app.schemas import DashboardStats
from app.services.dashboard import build_stats

router = APIRouter(prefix="/api/dashboard")


@router.get("/stats", response_model=DashboardStats, response_model_by_alias=True)
def stats(start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"),
          session: Session = Depends(get_session)):
    today = date.today()
    end = end or today
    start = start or today - timedelta(days=90)
    if start > end:
        raise AppError(422, "validation_error", "from must not be after to")
    return build_stats(session, start, end, today)
