import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import exists, func, insert, literal, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.errors import AppError
from app.models import Organization, SearchJob, SearchJobLead, SearchProgress, SourceConfig
from app.schemas import JobOut, ProgressOut, SearchCreate
from app.services.search import progress_key
from app.worker import HOST
from app.sources.provider import search_provider

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
    search_key = search_provider(get_settings())[0]
    bad = [k for k in [*body.sources, *((search_key, "practice_websites") if body.enrich else ())] if k not in available]
    if bad:
        raise AppError(422, "source_not_available", f"Source not available: {', '.join(bad)}")
    job = SearchJob(**body.model_dump(), host=HOST)
    session.add(job)
    return _save(session, job)


@router.post("/{job_id}/enrich-emails", response_model=JobOut, status_code=201)
def find_emails(job_id: str, session: Session = Depends(get_session)):
    """Find websites and emails for the leads of a finished search that were not enriched yet, as a new job."""
    src = _get_job(session, job_id)
    search_key, _, _ = search_provider(get_settings())
    available = set(session.scalars(select(SourceConfig.key).where(SourceConfig.status == "available")))
    off = [k for k in (search_key, "practice_websites") if k not in available]
    if off:
        raise AppError(422, "source_not_available", f"Source not available: {', '.join(off)}")
    todo = _to_enrich(src.id).subquery()
    n = session.scalar(select(func.count()).select_from(todo))
    if not n:
        raise AppError(409, "nothing_to_enrich", "Every lead of this search already has its emails searched")
    active = select(SearchJobLead.organization_id).join(SearchJob, SearchJob.id == SearchJobLead.search_job_id).where(
        SearchJob.enrich.is_(True), SearchJob.include_practices.is_(False), SearchJob.include_solo.is_(False),
        SearchJob.status.in_(("queued", "running")))
    if session.scalar(select(exists().where(todo.c.organization_id.in_(active)))):
        raise AppError(409, "already_running", "A Find emails job is already running for some of these leads")
    job = SearchJob(specialty=f"Find emails: {src.specialty}", state=src.state, city=src.city, target_count=n, include_practices=False,
                    include_solo=False, sources=["npi_registry"], enrich=True, host=HOST)
    session.add(job)
    session.flush()
    session.execute(insert(SearchJobLead).from_select(
        ["id", "search_job_id", "organization_id", "was_new"],  # id explicit: the Python-side default would repeat one uuid for every row
        select(func.gen_random_uuid(), literal(job.id), todo.c.organization_id, literal(False))))
    return _save(session, job)


def _to_enrich(job_id):
    """Leads of a search that enrichment has not covered yet (same rule as enrich_job_leads)."""
    return select(SearchJobLead.organization_id).join(Organization, Organization.id == SearchJobLead.organization_id).where(
        SearchJobLead.search_job_id == job_id, Organization.enrichment_status.in_(("not_run", "failed")))


@router.get("", response_model=list[JobOut])
def list_searches(session: Session = Depends(get_session)):
    jobs = session.scalars(select(SearchJob).order_by(SearchJob.created_at.desc()).limit(50)).all()
    left = dict(session.execute(
        select(SearchJobLead.search_job_id, func.count()).join(Organization, Organization.id == SearchJobLead.organization_id)
        .where(SearchJobLead.search_job_id.in_([j.id for j in jobs]), Organization.enrichment_status.in_(("not_run", "failed")))
        .group_by(SearchJobLead.search_job_id)).all())
    return [JobOut.model_validate(j).model_copy(update={"to_enrich": left.get(j.id, 0)}) for j in jobs]


def _progress(session: Session, specialty: str, state: str, city: str | None, include_subparts: bool, include_hospitals: bool):
    return session.scalar(select(SearchProgress).filter_by(**progress_key(specialty, state, city, include_subparts, include_hospitals)))


@router.get("/progress", response_model=ProgressOut)
def get_progress(specialty: str, state: str, city: str | None = None, include_subparts: bool = True,
                 include_hospitals: bool = False, session: Session = Depends(get_session)):
    row = _progress(session, specialty, state.upper(), city, include_subparts, include_hospitals)
    if row is None:
        return ProgressOut(leads_fetched=0, exhausted=False)
    return ProgressOut(leads_fetched=row.leads_fetched, exhausted=bool(row.cursor) and all(not c["slices"] for c in row.cursor.values()))


@router.delete("/progress", status_code=204)
def reset_progress(specialty: str, state: str, city: str | None = None, include_subparts: bool = True,
                   include_hospitals: bool = False, session: Session = Depends(get_session)):
    """Start over: the next search for these filters reads from the beginning again. Saved leads are kept."""
    row = _progress(session, specialty, state.upper(), city, include_subparts, include_hospitals)
    if row is not None:
        session.delete(row)
        session.commit()


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
    job.host = HOST  # resuming from this computer moves the job here: the one it ran on may be closed
    return _save(session, job)
