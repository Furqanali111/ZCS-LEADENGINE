import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.leads import salesperson
from app.db import get_session
from app.errors import AppError
from app.models import SavedSearch
from app.schemas import SavedSearchIn, SavedSearchOut

router = APIRouter(prefix="/api/saved-searches")


def _get(session: Session, saved_id: uuid.UUID) -> SavedSearch:
    s = session.get(SavedSearch, saved_id)
    if s is None:
        raise AppError(404, "not_found", f"Saved search {saved_id} not found")
    return s


@router.get("", response_model=list[SavedSearchOut])
def list_saved(session: Session = Depends(get_session)):
    return session.scalars(select(SavedSearch).order_by(SavedSearch.created_at.desc())).all()


@router.post("", response_model=SavedSearchOut, status_code=201)
def create_saved(body: SavedSearchIn, session: Session = Depends(get_session), name: str | None = Depends(salesperson)):
    s = SavedSearch(**body.model_dump(), created_by=name)
    session.add(s)
    try:
        session.commit()
    except IntegrityError:  # unique lower(name)
        session.rollback()
        raise AppError(409, "duplicate_name", "A saved search with this name already exists")
    session.refresh(s)
    return s


@router.delete("/{saved_id}", status_code=204)
def delete_saved(saved_id: uuid.UUID, session: Session = Depends(get_session)):
    session.delete(_get(session, saved_id))
    session.commit()
    return Response(status_code=204)


@router.post("/{saved_id}/touch", response_model=SavedSearchOut)
def touch_saved(saved_id: uuid.UUID, session: Session = Depends(get_session)):
    s = _get(session, saved_id)
    s.last_run_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(s)
    return s
