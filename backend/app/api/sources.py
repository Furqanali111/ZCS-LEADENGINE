from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import SourceConfig
from app.schemas import SourceOut

router = APIRouter(prefix="/api")


@router.get("/sources", response_model=list[SourceOut])
def list_sources(session: Session = Depends(get_session)):
    order = (SourceConfig.status != "available", SourceConfig.name)
    no_key = not get_settings().brave_api_key
    return [SourceOut(key=r.key, name=r.name, status=r.status, notes=r.notes, key_missing=no_key and r.key == "brave_search")
            for r in session.scalars(select(SourceConfig).order_by(*order))]
