from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import AppError
from app.schemas import DashboardStats, TeamRow
from app.services.dashboard import team_query, build_stats, team_window

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


@router.get("/team", response_model=list[TeamRow])
def team(range: Literal["today", "yesterday", "24h", "48h", "7d", "30d"] = "today", session: Session = Depends(get_session)):
    """What each salesperson did in the window, one lead counted once per person (see build_stats)."""
    lo, hi = team_window(range, date.today())
    return [TeamRow.model_validate(r) for r in session.scalar(select(team_query(lo, hi)))]
