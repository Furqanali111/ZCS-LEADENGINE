import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import AppError
from app.models import SearchJob, SourceConfig
from app.schemas import JobOut, SearchCreate

router = APIRouter(prefix="/api/search")


def _get_job(session: Session, job_id: str) -> SearchJob:
    try:
        job = session.get(SearchJob, uuid.UUID(job_id))
    except ValueError:
        job = None
    if job is None:
        raise AppError(404, "not_found", f"Search job {job_id} not found")
    return job


def _save(session: Session, job: SearchJob) -> SearchJob:
    session.commit()
    session.refresh(job)  # reload server-side values (updated_at etc.)
    return job


@router.post("", response_model=JobOut, status_code=201)
def create_search(body: SearchCreate, session: Session = Depends(get_session)):
    available = set(session.scalars(select(SourceConfig.key).where(SourceConfig.status == "available")))
    bad = [k for k in body.sources if k not in available]
    if bad:
        raise AppError(422, "source_not_available", f"Source not available: {', '.join(bad)}")
    job = SearchJob(**body.model_dump())
    session.add(job)
    return _save(session, job)


@router.get("", response_model=list[JobOut])
def list_searches(session: Session = Depends(get_session)):
    return session.scalars(select(SearchJob).order_by(SearchJob.created_at.desc()).limit(50)).all()


@router.get("/{job_id}", response_model=JobOut)
def get_search(job_id: str, session: Session = Depends(get_session)):
    return _get_job(session, job_id)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_search(job_id: str, session: Session = Depends(get_session)):
    job = _get_job(session, job_id)
    if job.status in ("completed", "cancelled", "failed"):
        raise AppError(409, "invalid_job_state", f"Cannot cancel a {job.status} job")
    job.cancel_requested = True
    if job.status in ("queued", "paused"):
        job.status = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
    return _save(session, job)


@router.post("/{job_id}/resume", response_model=JobOut)
def resume_search(job_id: str, session: Session = Depends(get_session)):
    job = _get_job(session, job_id)
    if job.status not in ("paused", "failed"):
        raise AppError(409, "invalid_job_state", f"Cannot resume a {job.status} job")
    job.status, job.error, job.cancel_requested = "queued", None, False
    return _save(session, job)
