"""Local in-process worker: one daemon thread runs the oldest queued search job at a time."""
import logging
import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, update

from app.models import SearchJob
from app.services.search import run_job

logger = logging.getLogger(__name__)

STALE_MINUTES = 15  # a live job rewrites its row at least every page or enriched lead, so an older updated_at means its app died


def pause_running_jobs(session) -> int:
    """Pauses 'running' jobs whose row has not moved for STALE_MINUTES: their app is gone. Live teammates' jobs stay."""
    stale = SearchJob.updated_at < func.now() - timedelta(minutes=STALE_MINUTES)
    count = session.execute(update(SearchJob).where(SearchJob.status == "running", stale)
                            .values(status="paused")).rowcount
    session.commit()
    return count


def claim_next(session_factory) -> UUID | None:
    """Atomically moves the oldest queued job to running, so two workers never take the same one."""
    oldest = (select(SearchJob.id).where(SearchJob.status == "queued")
              .order_by(SearchJob.created_at, SearchJob.id).limit(1).with_for_update(skip_locked=True).scalar_subquery())
    with session_factory() as session:
        job_id = session.scalar(update(SearchJob).where(SearchJob.id == oldest).values(status="running")
                                .returning(SearchJob.id))
        session.commit()
        return job_id


def run_next(session_factory) -> bool:
    """Runs one queued job if there is one. A crash fails that job, never the worker."""
    job_id = claim_next(session_factory)
    if job_id is None:
        return False
    try:
        run_job(session_factory, job_id)
    except Exception as e:
        logger.exception("search job %s crashed: %s", job_id, type(e).__name__)
        with session_factory() as session:
            session.execute(update(SearchJob).where(SearchJob.id == job_id).values(
                status="failed", error=type(e).__name__, finished_at=datetime.now(timezone.utc)))
            session.commit()
    return True


def start_worker(session_factory, poll_seconds: float = 2, stop: threading.Event | None = None) -> threading.Thread:
    stop = stop or threading.Event()

    def loop():
        while not stop.is_set():
            try:
                if run_next(session_factory):
                    continue
                with session_factory() as session:
                    pause_running_jobs(session)
            except Exception as e:  # database unreachable: keep polling
                logger.error("worker poll failed: %s", type(e).__name__)
            stop.wait(poll_seconds)

    thread = threading.Thread(target=loop, name="search-worker", daemon=True)
    thread.stop_event = stop
    thread.start()
    return thread
