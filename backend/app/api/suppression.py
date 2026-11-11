import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import AppError
from app.models import SuppressionEntry
from app.schemas import SuppressionIn, SuppressionOut
from app.services import suppression

router = APIRouter(prefix="/api/suppression")


@router.get("", response_model=list[SuppressionOut])
def list_entries(session: Session = Depends(get_session)):
    return session.scalars(select(SuppressionEntry).order_by(SuppressionEntry.created_at.desc(), SuppressionEntry.id)).all()


@router.post("", response_model=SuppressionOut, status_code=201)
def create_entry(body: SuppressionIn, session: Session = Depends(get_session)):
    """Phone entries match digits only (phone and fax). Email entries are stored lowercased but match no lead until slice 3 stores emails."""
    try:
        return suppression.add_entry(session, body.kind, body.value, body.reason)
    except ValueError as e:
        raise AppError(422, "validation_error", str(e))


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: uuid.UUID, session: Session = Depends(get_session)):
    """Removing an entry does not change any lead status."""
    entry = session.get(SuppressionEntry, entry_id)
    if entry is None:
        raise AppError(404, "not_found", f"Suppression entry {entry_id} not found")
    session.delete(entry)
    session.commit()
    return Response(status_code=204)
